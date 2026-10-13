# How it works

A conversion runs in five stages. Each one caches its output, so changing only the music, for example, skips straight
to the mix.

```
module.html ──► 1. narration ──► 2. timeline ──► 3. picture ──► 5. mux ──► module.mp4
                  (Kokoro)                         (Chromium + x264)   ▲      + .srt / .vtt
                                     └──────────► 4. sound ────────────┘
                                                 (voice + music, ducked, normalised)
```

The code lives in [`src/html2mp4/cli.py`](../src/html2mp4/cli.py) (conversion),
[`studio.py`](../src/html2mp4/studio.py) and [`studio.html`](../src/html2mp4/studio.html) (the web app), and
[`music.py`](../src/html2mp4/music.py) (music synthesis).

## 1. Narration

The `scenes` list is read straight from the module's script. Each chunk is voiced with Kokoro-82M at 24 kHz, and
leading and trailing silence is trimmed, keeping 30 ms. Clips are cached by voice, speed and a hash of the text, so
re-rendering a module only voices sentences that changed.

Kokoro runs on the CPU with at most four threads. That leaves room for rendering, and stops the voice engine from
thrashing when the machine is busy.

## 2. Timeline

Chunks are laid end to end with fixed pauses:

| Gap | Length |
|---|---|
| Before the first word | 0.6 s |
| Between chunks | 0.45 s |
| Before a new slide | 0.9 s extra |
| After the last word | 1.6 s hold, with the sound fading out over the last 0.8 s |

Each chunk's elements are revealed at the moment the chunk starts, which is the rule the module's own player follows.
Before moving to the next slide, the renderer measures how long that slide's longest transition or animation runs
(delay plus duration, read from computed styles). If it would still be running, the slide is held until it finishes,
plus 0.6 s.

## 3. Picture

Headless Chromium (through Playwright) opens the module with the viewport set to the stage size. The device pixel
ratio is set so the stage is drawn natively at the output resolution: 2.0 for 1440p and 1.5 for 1080p from a 1280×720
stage. Nothing is upscaled.

Animation is driven by seeking, never by waiting:

1. When a chunk starts, the renderer toggles `active` and `on` classes exactly as the module's player would.
2. Every resulting CSS transition or animation is collected with `document.getAnimations()` and paused.
3. For each frame at time *t*, each animation's `currentTime` is set to *t* minus the moment it was created, and the
   frame is captured.

Because time is set rather than measured, every frame is exact regardless of how long capture takes. The frame range
is split across worker processes, half the CPU cores by default, which render their segments in parallel. The
segments are then joined without re-encoding.

### Encoding

Frames are converted to BT.709 4:2:0 with a Lanczos scaler and encoded with x264 using High profile, CRF 17,
`preset slow`, `tune animation` and `aq-mode=3`. The file is written with `faststart`, so it can play while still
downloading.

These settings were chosen by measurement. Real module frames were captured losslessly and encoded at several
settings:

- At CRF 17, the result is within about 0.5 dB PSNR of an uncompressed 4:2:0 copy, at roughly 2–3 MB per minute.
- Lower CRF values grow the file without a visible gain.
- The remaining limit is 4:2:0 itself: web-compatible video stores colour at half resolution. 1440p keeps colour
  detail at the stage's own resolution, which is why it is the default.

Previews use `preset veryfast`, trading file size for speed.

## 4. Sound

**Voice.** The narration track goes through a 70 Hz high-pass filter, gentle compression (2.2:1 above −21 dB) and
two-pass EBU R128 normalisation to −16 LUFS with a −1.5 dBTP ceiling. It is then resampled to 48 kHz.

**Music.** The bed is looped to the video's length and high-passed at 140 Hz. This is standard practice under
narration: it clears space for the voice and keeps the music audible on laptop speakers. The bed is then normalised
and shaped by a gain curve:

- it sits 8, 12 or 17 dB below the voice while it speaks (*present*, *balanced*, *subtle*);
- it rises 6 dB in pauses, starting 0.35 s after a sentence ends and dropping back 0.25 s before the next one begins;
- it moves down in 0.3 s and up in 0.9 s, so there are no audible jumps;
- it fades in over the first 2 s.

The mix is limited, normalised again to −16 LUFS and encoded as AAC at 192 kb/s.

**Built-in music** is synthesised by `music.py`: detuned saw pads, a plucked arpeggio or an FM electric piano over a
four-chord progression at 80 BPM, with convolution reverb. Each bed is a seamless 48-second loop. No samples or AI
models are involved, so the output is free of licensing questions.

## 5. Captions and mux

Captions are built from the same text the narrator reads. Each chunk is split at sentence boundaries, with very short
sentences merged into the next, into cues of at most two lines of about 42 characters. Within a chunk, cues are timed
in proportion to their length. The result is written as `.srt` and `.vtt`, and embedded in the MP4 as a
`mov_text` track that players can switch on and off.

FFmpeg combines the cached picture, the mixed sound and the captions without re-encoding the video.

## Caching

| Cache | Key | Effect |
|---|---|---|
| Narration clips | voice, speed, sentence text | A new voice or pace re-voices only what's needed |
| Rendered picture | file content, timeline, resolution, encoder settings | A new music choice or volume re-mixes in seconds |
| Music beds and Studio previews | style | Generated once |

All caches live in `~/.cache/html2mp4`, or `HTML2MP4_CACHE` if set, and can be deleted at any time.

## Studio

The Studio is a FastAPI app bound to `127.0.0.1` with a single-page front end. Conversions run in two lanes, each
processing one job at a time:

- **Videos** run at lower OS priority.
- **Previews** start immediately. While a preview is being made, any video in progress pauses its frame workers, then
  resumes exactly where it stopped. A preview during a full render takes about 45 seconds instead of minutes.

A new preview replaces an older one that's still running. Every job can be cancelled. Cancellation takes effect at the
next sentence or frame, and leaves no partial files behind.

Jobs belong to the server, not the page. Reloading or closing the browser doesn't affect them, and on load the page
reconnects to anything still in progress. Finished and failed videos are recorded in the cache, so the
"Your videos" list survives restarts. A job that was interrupted by the Studio closing is marked as such.

## Fidelity

The aim is a faithful recording of the module. This section lists exactly where the video can differ.

**Identical to the page**

- All content: slides, text, colours, fonts and graphics. Chromium renders the original file, with the page's own HTML,
  CSS and assets.
- All animation: which element appears with which chunk (`data-c`), its delay (`data-d`), its CSS timing curve and
  duration, and the slide-to-slide transition. Elements appear exactly when their chunk starts, as in the page's own player.

This was verified frame by frame on a real 24-chunk module. The original page was driven by its own player through its
seek bar and captured after each step, then compared with the MP4 at the same moments. Every step matched at
38–47 dB PSNR, median 41 dB. The only differences were compression noise along edges, with no difference in content or
timing.

**Necessarily different**

- **Voice and pacing.** In a browser, a module speaks with whichever system voice the viewer's computer has, so its
  timing varies from machine to machine. The video uses Kokoro, so each step lasts as long as its sentence takes to
  say, with the pauses listed under [Timeline](#2-timeline).
- **Slides are held until their animations finish.** In the browser, a fast voice can move on before a delayed
  animation completes. The video holds the slide so it's always seen complete.
- **Player controls are hidden.** A module's own control bar (`#bar`) and start overlay (`#start`) aren't part of the slides.

**Added, and optional**

- Background music (`--music none` turns it off).
- The caption track (switchable, never drawn into the picture).
- 0.6 s of silence before the first word, and a 1.6 s hold on the final slide while the sound fades.
