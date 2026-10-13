# html2mp4

Turn a narrated HTML slide module into a professional, e-learning-ready MP4:
1080p video, a natural neural voiceover, captions you can switch on or off, and an optional background music bed.

Everything runs locally on your machine: no cloud services, no API keys, no per-video cost.

```bash
html2mp4 my-module.html          # → my-module.mp4 + my-module.srt + my-module.vtt
```

## What you get

| | |
|---|---|
| **Picture** | 1920×1080, 30 fps, H.264 High, BT.709 colour. Every animation is frame-exact and lands on the word that triggers it. |
| **Voice** | [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) neural text-to-speech (open source, Apache-2.0), running locally. Natural pauses between sentences and before slide changes. |
| **Sound** | Voice clean-up and EBU R128 loudness normalisation to −16 LUFS (the online-learning standard). The music bed automatically ducks under speech. |
| **Captions** | An embedded subtitle track (switch on/off in VLC, QuickTime, most LMS players) plus `.srt` and `.vtt` files. Line breaks follow sentences, with no orphan words. |
| **Music** | Three built-in royalty-free beds, synthesised in code (no AI, no licensing): `gentle-pulse` (default), `calm-pad`, `warm-keys`. Or pass any audio file. |

## Setup (once)

Requirements: macOS or Linux, [ffmpeg](https://ffmpeg.org) (`brew install ffmpeg`), and Python 3.10–3.12 (or [uv](https://docs.astral.sh/uv/)).

```bash
git clone <this repo> html2mp4
cd html2mp4
./setup.sh
```

The first conversion downloads the voice model (~330 MB) from Hugging Face; after that, everything works offline
(apart from any web fonts your HTML loads).

## Usage

```bash
source .venv/bin/activate

html2mp4 module.html                              # default: af_heart voice, 0.90× speed, gentle-pulse music
html2mp4 module.html --music none                 # no music
html2mp4 module.html --music calm-pad             # another built-in bed
html2mp4 module.html --music ~/Music/track.mp3    # your own (royalty-free) track
html2mp4 module.html --voice am_michael           # a different narrator
html2mp4 module.html --scenes 1 -o preview.mp4    # quick preview of the first scene only
```

| Option | Default | |
|---|---|---|
| `-o, --out` | next to the HTML | Output `.mp4` path. Captions are written alongside it. |
| `--voice` | `af_heart` | Kokoro voice: `af_heart`, `af_bella` (US female), `am_michael`, `am_fenrir` (US male), `bf_emma`, `bm_george` (UK). [Full list](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md) |
| `--speed` | `0.90` | Narration speed. |
| `--music` | `gentle-pulse` | `gentle-pulse`, `calm-pad`, `warm-keys`, `none`, or a path to an audio file. |
| `--music-level` | `20` | How many dB the music sits under the voice while it speaks (it rises 6 dB in pauses). |
| `--scenes N` | all | Render only the first N scenes. |
| `--workers N` | half your CPU cores | Parallel render processes. |

A 2–3 minute module takes about 6–7 minutes on an Apple M-series laptop. The rendered picture and the voice clips
are cached, so re-running with a different `--music` takes well under a minute.

## Authoring a module

Open [`examples/example.html`](examples/example.html): it's a complete, minimal module (click it in a browser to step
through). A module needs:

1. **A fixed-size stage.** `#frame > #stage` with a 16:9 size (e.g. 1280×720). The stage is scaled to 1920×1080.
2. **One `<section class="slide" id="…">` per scene.** The visible one has the class `active`.
3. **The narration in the page script**, as one list. Each chunk is a sentence, voiced exactly as written:
   ```js
   var scenes = [
     {id:'s0', chunks:["First sentence.", "Second sentence."]},
     {id:'s1', chunks:["…"]}
   ];
   ```
   Use double quotes around each sentence.
4. **Cues on animated elements.** `data-c="N"` makes an element appear (class `on`) when sentence N of its scene
   starts. `data-d="1.5"` adds a 1.5 s delay, exposed to CSS as `var(--d)`. Animate with CSS transitions or animations.

`#bar` and `#start` (an in-page player bar and play overlay, if your template has them) are hidden in the video.

Tips:
- Write numbers and abbreviations the way they should be spoken; the voice reads the text literally.
- Check names and jargon in a `--scenes 1` preview before rendering the full module.

## How it works

1. **Narration.** Each sentence is voiced with Kokoro and cached by its text, voice and speed.
2. **Timeline.** Sentences are laid out with breathing room. Each slide is held until all of its animations have finished.
3. **Picture.** Headless Chromium (via Playwright) loads the page. Every CSS transition is paused and seeked to the exact
   time of each frame, and frames are rendered in parallel segments.
4. **Audio.** The voice is cleaned up and normalised, then the music is looped, ducked under speech, mixed, limited and normalised.
5. **Mux.** ffmpeg combines the picture, sound and captions into a web-optimised (`faststart`) MP4.

The cache lives in `~/.cache/html2mp4` (override with `HTML2MP4_CACHE`) and can be deleted at any time.
`html2mp4-music <dir>` writes the built-in music beds to a folder if you want to listen to them.

## Troubleshooting

- **`ffmpeg not found`**: install it (`brew install ffmpeg`).
- **`No var scenes = [...] narration block found`**: the HTML doesn't follow the template (see *Authoring a module*).
- **A word is mispronounced**: respell it the way it should sound in the narration (for example "S Q L" or "sequel"
  instead of "SQL"), or rephrase it.
- **Fonts look different from the browser**: the page's web fonts must be reachable while rendering.
