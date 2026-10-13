# Build prompt

This is a single prompt for an AI coding assistant to rebuild Narrated Slides Studio from scratch. It records the
requirements, design decisions and pitfalls found while building it. It is also useful as a compact specification
when changing the project.

````markdown
Build "Narrated Slides Studio": a local, open-source tool that turns narrated HTML slide modules into finished
training videos (MP4 with voiceover, background music and captions). Target users include non-technical HR staff
on Apple-silicon Macs. Everything runs locally: no cloud APIs, no accounts, no telemetry.

## Input format (the "module")
A single self-contained HTML file:
- `#frame > #stage`: a fixed 16:9 stage (normally 1280×720). It may contain an in-page player bar `#bar` and a
  start overlay `#start`; both must be hidden in the video.
- One `<section class="slide" id="sN">` per scene; the visible slide has class `active`.
- Narration in the page script: `var scenes = [{id:'s0', chunks:["sentence", ...]}, ...]` (double-quoted strings).
- Elements tagged `data-c="N"` gain class `on` when chunk N of their slide starts (elements on earlier slides stay
  `on`). Optional `data-d="1.5"` is a delay, exposed to CSS as `--d`. Animation is CSS transitions/animations only.
Validate input with friendly errors: no scenes list, empty narration, scene id with no matching element, no #stage.

## Non-negotiable: fidelity
The video must reproduce the page exactly: same content, same animations, same cue rule (elements appear exactly
when their chunk starts, with no lead), same slide transition. Never inject overlays or fades over the picture.
Allowed differences, documented in the README: voice timing (it comes from the TTS), short fixed pauses, holding a
slide until its last animation finishes, hidden player controls, optional music, captions.
Verify fidelity by driving the original page through its own player and comparing frames against the MP4 (PSNR).

## Pipeline (Python package `html2mp4`, src layout)
1. Narration: Kokoro-82M (`kokoro` pip package) TTS, local, 24 kHz, per chunk. Trim silence (keep 30 ms). Cache by
   voice+speed+text hash. Curated voices: af_heart (default), af_bella, am_michael, am_fenrir, bf_emma, bm_george;
   lang code = first letter of the voice id. Default speed 0.90. Limit torch to ≤4 threads. Load each pipeline once
   and serialise synthesis with a lock.
   Gotchas: (a) espeak-ng (the fallback phonemizer) silently ignores data paths longer than ~160 chars and resolves
   symlinks, so copy espeakng_loader's data dir into a short cache path when the path is long; (b) install
   en_core_web_sm as a direct-URL dependency; (c) set HF_HUB_VERBOSITY=error.
2. Timeline: 0.6 s pre-roll, 0.45 s between chunks, +0.9 s before each slide, slide held until max(delay+duration)
   of its elements' computed transitions/animations + 0.6 s, 1.6 s end hold, 0.8 s audio fade-out.
3. Picture: Playwright headless Chromium, viewport = stage size, device_scale_factor = output_width/stage_width
   (native rendering, never upscaled). Hide #bar/#start, remove #frame inset and any #stage transform. Drive time
   by seeking: toggle classes per chunk, collect `document.getAnimations()`, pause each, and set `currentTime` per
   frame from the moment it was created. 30 fps.
   Gotcha: CDP `Page.captureScreenshot` IGNORES the emulated DPR. Pass `clip:{x,y,width,height,scale}` explicitly,
   and assert that the first frame's PNG header matches the target size.
   Render frame ranges in parallel worker processes (default: half the cores), each piping PNGs to its own ffmpeg,
   then concat the segments with stream copy. Workers report progress through a multiprocessing.Manager queue.
4. Encoding: ffmpeg scale with `out_color_matrix=bt709:out_range=tv:flags=lanczos+accurate_rnd+full_chroma_int+full_chroma_inp`,
   libx264 High, yuv420p, CRF 17, preset slow, tune animation, aq-mode=3, BT.709 tags, faststart. Give each worker
   cpu/workers threads. Quality presets: 1440p (default) and 1080p. Previews use preset veryfast.
5. Audio: voice → highpass 70 Hz → compressor (2.2:1 @ −21 dB) → two-pass loudnorm −16 LUFS / −1.5 dBTP → 48 kHz.
   Music: loop to length, highpass 140 Hz, normalise, then a ducking gain curve: music sits 17/12/8 dB under the
   voice while speaking (subtle/balanced/present, default balanced) and rises +6 dB in pauses (duck 0.25 s before
   speech, release 0.35 s after; 0.3 s attack / 0.9 s release smoothing). 2 s fade-in. Limiter, final two-pass
   loudnorm, AAC 192k.
6. Captions: from the narration text. Split at sentence boundaries (merge sentences under 24 chars), balanced cues
   of ≤2 lines × ~42 chars, no orphan words, timed proportionally within each chunk's audio. Write .srt and .vtt,
   and embed a switchable mov_text track (never burned in).
7. Mux the cached video, final audio and subtitles (video stream copy). Title metadata from <title>.
Cache rendered pictures by file content + timeline + size + encoder settings, so a change to music only re-mixes.
Bump a RENDER_VERSION constant whenever frame output changes.

## Music (no AI, royalty-free)
`music.py` synthesises three seamless 48 s loops in numpy/scipy (Am7–Fmaj7–Cadd9–G at 80 BPM, convolution reverb):
gentle-pulse (pads + plucked arpeggio, default), calm-pad, warm-keys (FM e-piano). Deterministic seed per style.
Generated on first use into the cache. Users may also supply their own audio file.

## Commands
- `html2mp4 module.html [-o out.mp4] [--voice] [--speed] [--music NAME|PATH|none] [--music-volume] [--quality]
  [--preview SECONDS] [--scenes N] [--workers N]`
- `html2mp4-studio` (local web app), `html2mp4-music [DIR]`
- Public API: `convert(html, out, ..., progress=cb(fraction,label), cancel=threading.Event, nice=0, pausable=False)`;
  raises ConversionError (user-facing message) or Cancelled.
- Env: HTML2MP4_CACHE (~/.cache/html2mp4), HTML2MP4_OUTPUT (~/Downloads/Narrated Videos), HTML2MP4_NO_BROWSER.
- ffmpeg: use the system binary if present, else imageio-ffmpeg's static build (no Homebrew).

## Studio (web app)
FastAPI + uvicorn bound to 127.0.0.1 (port 8765 or the next free one), opening the browser automatically. A single
self-contained HTML page (no build step, no CDN, system fonts, light and dark mode, responsive), designer-level,
calm and intuitive. Flow:
1. Drop or browse an .html file → show title, slide count, sentence count, estimated length, expandable narration script.
2. Narrator: six voice tiles with ▶ previews (pre-generate samples in the background at startup); pace segmented
   control (Relaxed 0.85 / Natural 0.90 / Brisk 1.0).
3. Music: tiles (No music, three beds with ▶ previews), "upload your own track", volume control (Subtle/Balanced/Present).
4. Quality: "Sharpest · 1440p" (default) / "Faster · 1080p".
5. "Preview 10 s" renders just the opening seconds, plays inline with captions, and shows a "settings changed,
   preview again" hint if settings change afterwards.
6. "Create video" shows a progress bar with steps (Voiceover, Timing, Animation, Sound mix, Finishing) and an ETA,
   then an inline player with captions, Download, .srt/.vtt and Show in Finder.
7. "Your videos" library with thumbnails; history persisted in the cache.
Job engine requirements (learned the hard way):
- Two lanes, one job each: previews and full videos. A preview must never wait behind a video: while a preview
  runs, the video's frame workers pause cooperatively (shared Event checked per frame) and then resume where they
  stopped. Video renders also run at nice 10.
- Cancel for every queued or running job, stopping at the next sentence or frame with no partial files left. A new
  preview cancels older previews.
- Jobs belong to the server: reloading or closing the page doesn't stop them; on load the page reconnects via
  /api/active. Waiting jobs say what they're waiting for. Interrupted jobs are marked failed on restart.
- `[hidden]{display:none!important}` (component display rules otherwise override `hidden`).

## Distribution
- `setup.sh`: installs uv to ~/.local/bin if missing (no admin), `uv venv --python 3.11`, `uv pip install -e .`,
  `playwright install chromium`, pre-downloads the voice model and music beds. Idempotent.
- `studio.sh`, `Install.command` and `Open Studio.command` (double-click launchers; document the first-run
  Gatekeeper "Open Anyway" step).
- pyproject (hatchling, python >=3.10,<3.13, console scripts, MIT, metadata), .gitignore.
- Docs written like a mature open-source project, not AI-sounding (no emoji, no marketing words, specific numbers):
  README (overview, screenshot, quick start, CLI, module format, requirements, docs index, credits),
  docs/getting-started.md (for non-technical users), docs/authoring.md, docs/cli.md, docs/how-it-works.md (with a
  Fidelity section), docs/troubleshooting.md, CHANGELOG (Keep a Changelog), CONTRIBUTING, SECURITY, LICENSE (MIT),
  GitHub issue forms and PR template. Include examples/example.html (a neutral two-slide module).

## Definition of done
- `html2mp4 examples/example.html` produces an MP4 whose resolution matches the setting (check with ffprobe),
  with video, audio and subtitle streams, at −16.0 LUFS integrated.
- Frame-by-frame comparison against the original page via its own player: every narration step ≥ ~38 dB PSNR.
- Studio tested end to end in a browser: upload, voice/music previews, 10 s preview, create, cancel, reload
  mid-render, and a preview during a full render that completes in under ~1 minute.
- A fresh clone installs with Homebrew removed from PATH and converts the example.
````
