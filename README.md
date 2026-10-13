# Narrated Slides Studio (html2mp4)

Turn a narrated HTML slide module into a professional, e-learning-ready MP4:
1080p video, a natural neural voiceover, captions you can switch on or off, and an optional background music bed.

Everything runs locally on your machine: no cloud services, no API keys, no per-video cost.

- **Non-technical users:** follow **[GETTING-STARTED.md](GETTING-STARTED.md)**. You'll use the Studio, a web page
  where you drag in a file, pick a voice and music, and download the video.
- **Command line:** `html2mp4 my-module.html` → `my-module.mp4` + `.srt` + `.vtt`

## What you get

| | |
|---|---|
| **Picture** | 2560×1440 (default) or 1920×1080, 30 fps. The slides are drawn natively at that size, never upscaled. H.264 High 4:2:0, BT.709, web-optimised (`faststart`), about 3 MB per minute at 1440p. Every animation is frame-exact and starts with the sentence that triggers it. |
| **Voice** | [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) neural text-to-speech (open source, Apache-2.0), running locally. Natural pauses between sentences and before slide changes. |
| **Sound** | Voice clean-up and EBU R128 loudness normalisation to −16 LUFS (the online-learning standard). The music bed's bass is cut so it carries on laptop speakers, and it dips under speech. Three volume levels. |
| **Captions** | An embedded subtitle track (switch on/off in VLC, QuickTime, most LMS players) plus `.srt` and `.vtt` files. Line breaks follow sentences, with no orphan words. |
| **Music** | Three built-in royalty-free beds, synthesised in code (no AI, no licensing): `gentle-pulse` (default), `calm-pad`, `warm-keys`. Or pass any audio file. |

## Setup (once)

Requirements: macOS on Apple silicon (M1 or later). No Homebrew, admin rights or system Python needed: `setup.sh`
installs [uv](https://docs.astral.sh/uv/), which installs Python, the libraries, a static ffmpeg build and headless Chromium
into this folder and your user caches.

```bash
mkdir -p ~/Downloads/narrated-video && cd ~/Downloads/narrated-video
git clone https://github.com/akash-adhikary/narrated-slides-to-video.git
cd narrated-slides-to-video
./setup.sh
```

Setup downloads the voice model (~330 MB) once. After that, everything works offline
(apart from any web fonts your HTML loads). If a system `ffmpeg` is on your PATH it is used; otherwise the bundled one is.

### Platforms

| | |
|---|---|
| macOS, Apple silicon | Supported and tested. A 2-minute module renders in about 4 minutes on an M4. |
| macOS, Intel | Untested. PyTorch no longer ships current builds for Intel Macs, so the voice engine may not install. |
| Linux | Should work (`./setup.sh`, `./studio.sh`); untested. |
| Windows | Not packaged yet. The Python code is portable, but there's no Windows installer or launcher yet. |

## Studio (web interface)

```bash
./studio.sh              # or double-click "Open Studio.command"
```

This opens `http://127.0.0.1:8765` in your browser, served only to this computer:

- upload a module and read its narration script
- preview the six voices and three music beds, or upload your own royalty-free track
- watch live progress, then play the result with captions and download the MP4 / `.srt` / `.vtt`
- see every video you've made

Videos are saved to `~/Downloads/Narrated Videos` (override with `HTML2MP4_OUTPUT`).

## Command line

```bash
source .venv/bin/activate

html2mp4 module.html                              # default: af_heart voice, 0.90× speed, gentle-pulse music
html2mp4 module.html --music none                 # no music
html2mp4 module.html --music calm-pad             # another built-in bed
html2mp4 module.html --music ~/Music/track.mp3    # your own (royalty-free) track
html2mp4 module.html --voice am_michael           # a different narrator
html2mp4 module.html --music-volume present      # louder music (subtle | balanced | present)
html2mp4 module.html --preview 10 -o preview.mp4  # just the first 10 seconds, to try settings
html2mp4 module.html --quality 1080p              # Full HD instead of 1440p (faster, a little smaller)
```

| Option | Default | |
|---|---|---|
| `-o, --out` | next to the HTML | Output `.mp4` path. Captions are written alongside it. |
| `--voice` | `af_heart` | Kokoro voice: `af_heart`, `af_bella` (US female), `am_michael`, `am_fenrir` (US male), `bf_emma`, `bm_george` (UK). [Full list](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md) |
| `--speed` | `0.90` | Narration speed. |
| `--music` | `gentle-pulse` | `gentle-pulse`, `calm-pad`, `warm-keys`, `none`, or a path to an audio file. |
| `--music-volume` | `balanced` | `subtle`, `balanced`, `present` (17 / 12 / 8 dB under the voice while it speaks, rising 6 dB in pauses), or a number of dB. |
| `--quality` | `1440p` | `1440p` (sharpest) or `1080p`. |
| `--preview S` | | Render only the first S seconds, quickly, to audition voice, pace and music. |
| `--scenes N` | all | Render only the first N scenes. |
| `--workers N` | half your CPU cores | Parallel render processes. |

A 2–3 minute module takes about 5–8 minutes at 1440p on an Apple M-series laptop (less at 1080p). The rendered picture and the voice clips
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

## Fidelity: what the video does and doesn't change

The goal is a faithful recording of the HTML. The page's own HTML, CSS, text and animations are used unchanged.

**Identical to the page**
- Every slide, text, colour, font and graphic. The page is rendered by Chromium from the original file.
- Every animation: which element appears on which sentence (`data-c`), its delay (`data-d`), its CSS transition curve and duration,
  and the slide-to-slide transition. The page's own rule is reproduced exactly: elements of sentence N appear when sentence N starts.
- Checked with a frame-by-frame comparison: the original page, driven by its own player, against the MP4 at all 24 narration steps of
  a real module. Every step matched to 38–47 dB PSNR. The only differences are compression noise along edges, with no difference in content or timing.

**Necessarily different**
- **Voice and timing.** In the browser, the page speaks with whatever system voice the viewer has, so its timing varies from
  computer to computer. The video uses the Kokoro voice, so each step lasts as long as its sentence takes to say, plus a short
  breath (0.45 s) between sentences and a pause (0.9 s) before each slide change.
- **Slides are held until their animations finish.** If a slide's last animation (e.g. a delayed `data-d`) would still be running
  when the narration moves on, the slide is held a moment longer so it's seen complete. The page itself would cut it off if the voice were faster.
- **Player controls are hidden.** The page's own play bar (`#bar`) and play overlay (`#start`) aren't part of the slides.

**Added (optional)**
- Background music (`--music none` to turn off) and the caption track (switchable, never burned into the picture).
- 0.6 s of silence before the first word, and a 1.6 s hold on the final slide while the sound fades out.

## How it works

1. **Narration.** Each sentence is voiced with Kokoro and cached by its text, voice and speed.
2. **Timeline.** Sentences are laid out with breathing room. Each slide is held until all of its animations have finished.
3. **Picture.** Headless Chromium (via Playwright) loads the page. Every CSS transition is paused and seeked to the exact
   time of each frame, and frames are rendered in parallel segments.
4. **Audio.** The voice is cleaned up and normalised, then the music is looped, ducked under speech, mixed, limited and normalised.
5. **Mux.** ffmpeg combines the picture, sound and captions into a web-optimised (`faststart`) MP4.

The Studio is a small FastAPI app (`src/html2mp4/studio.py` + `studio.html`) bound to 127.0.0.1. It renders one video at a
time and queues the rest.

The cache lives in `~/.cache/html2mp4` (override with `HTML2MP4_CACHE`) and can be deleted at any time.
`html2mp4-music <dir>` writes the built-in music beds to a folder if you want to listen to them.

## Troubleshooting

- **"This file doesn't contain a narration script"**: the HTML doesn't follow the template (see *Authoring a module*).
- **The Studio page won't load**: the Studio must be running. Start `./studio.sh` and keep its window open.
- **A word is mispronounced**: respell it the way it should sound in the narration (for example "S Q L" or "sequel"
  instead of "SQL"), or rephrase it.
- **Fonts look different from the browser**: the page's web fonts must be reachable while rendering.
