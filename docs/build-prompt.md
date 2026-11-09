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

## Write page: script -> slides (module HTML)
Sits in front of everything above: the Studio opens on a "Write" tab (then "Create video" and "Settings"). Making videos stays
local; this part calls Claude (Claude Opus 5.5, `claude-opus-5-5`, via the official `anthropic` SDK, streaming, structured
output with `output_config.format`, `fallbacks:"default"` + beta `server-side-fallback-2026-07-01`, system prompt cached).
All Claude calls live in one `ai.py` with plain-language errors; a missing key is a friendly message, never a traceback.
- Script formats (auto-detected): (a) "Scene N: Title (0:00 to 0:30)" / "On screen: ..." / narration paragraphs, first line = title;
  (b) Title/Subtitle/`## Slide`/Show/Say/Note. Split paragraphs into sentences without splitting inside curly or straight
  quotes, after abbreviations, or after "St." inside a word (match whole words: "honest." is not "St."). Narration is copied
  verbatim; only visuals come from Claude. Errors name the line.
- `compose.py` generates everything that must be exact in code: stage, theme (CSS variables incl. one `--c-<name>` per brand
  colour and a fixed type scale 96/64/44/28/22/16), narration list (JSON, `</` escaped), footer+logo, a review player, and a
  no-AI "quick layout". Brand: dark/light roles, fonts, two logo slots (on dark / on light), design rules, glossary.
  Kit fonts are embedded as `@font-face`.
- Claude returns per slide `{id, layout, summary, html, css}`. Reject (statically) scripts, event handlers, outside links,
  images, `url()`, `@import`, animation/keyframes, `position:fixed`, and any selector not starting with `#<slide id>`.
  Prompt rules that mattered: reveal with `data-c` (+ `data-cue="exact words"` for items named in turn); flex/grid not
  absolute positions; boxes sized to their text with 16px padding; 24px gaps; no connector lines, arrows or hubs; one visual
  language across slides; only the fixed font sizes; colours only via variables; use given on-screen text verbatim; never
  invent facts; apply brand rules; headline case via CSS.
- Checker (`verify.py`, Playwright): for every narration step of every slide, jump to the fully revealed state and measure
  in-page: text rect vs the nearest ancestor with a border/background (spills), SVG text crossing shape edges, text/box
  overlaps (`data-overlay` opts out), safe-area bounds (24px margins, above the footer), computed font size x CTM scale vs
  the scale, contrast vs nearest solid background (skip gradient/`background-clip:text`), words not in the script (stem
  inflections; ignore contractions) as a warning, banned terms, page errors. Parse HTML with a real parser, not regexes:
  Claude writes single-quoted attributes. Problems go back with the first failing step's screenshot (max 2 fix rounds),
  then a design review of final-state screenshots (`must` = fix, `nice` = note; tell it to ignore the footer; screenshots
  are shrunk, so don't judge small sizes from them). Report only what is true: never claim "checked" unless it was.
- Cue timing: the TTS reports word start times (Kokoro tokens); save them per sentence (relative to the trimmed clip), and in
  the renderer set each cued element's `--d` from them before measuring spans and rendering. The review player estimates it.
- Pronunciation glossary changes the spoken text only (captions/slides keep the written form). Banned terms are enforced.
- Brand kit import: drop a folder/zip, PDF, logos, fonts, or a module. Read fonts (family, variable weight axis), classify
  logos (light/dark, primary/icon/stacked), read modules (palette, fonts, logos, compact style reference), have Claude read the
  PDF into palette/roles/fonts/rules (keep only hex codes that appear in the PDF; heuristics without a key). Review before
  applying; settings in `~/.config/html2mp4` (0600). Pages and scripts must revalidate (`Cache-Control: no-cache`).
- Projects on disk (`Modules/<name>/`: project.json, script.txt, module.html, versions/vN.html+json): every design, revision
  and restore is a new version. Revisions take free text, scope (module or slide) and moments ("at 2:51" is mapped to a slide
  from approximate start times). Editing the script redesigns only changed slides. Quick-layout projects upgrade with
  "Design with Claude".
- Write page UI: script box with live parse status, suggestions (typos/clarity/risky wording/pronunciation, accepted one
  by one; quotes must exist in the script), design job with streamed progress ("planning the layouts", then "n of 6 done";
  ~4-8 min, ~$1), review (preview iframe synced with a slide list, version select/restore, checker notes, feedback box),
  "Use these slides to make the video" hands the module to the Create page. Jobs survive reloads.
- Tests (pytest, no network): parser, composer, checker (clean and deliberately broken slides), brand kit with synthetic
  assets, a fake Claude for the design/fix/review loop, projects, and the Studio API.

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
- The Write page turns a real script (with the Scene/On screen format) into slides that pass the checker, in the brand,
  and the resulting module converts to a video in which items appear on the words that name them.
````
