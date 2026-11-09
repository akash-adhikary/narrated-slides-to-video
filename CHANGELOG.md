# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org).

## [Unreleased]

## [0.4.0] - 2026-11-09

### Added
- **Write page**: paste a script and Claude designs the slides. Scripts can use `Scene N: Title` / `On screen:` / narration
  paragraphs, or `Title:` / `## Slide` / `Show:` / `Say:`. See `docs/scripts.md`.
- **Layout checker**: every narration step of every slide is rendered and measured for text that doesn't fit its box,
  overlaps, content outside the margins, font sizes outside a fixed type scale, low contrast, banned terms and script
  errors. Problems are fixed automatically, with screenshots, in up to two rounds, followed by a design review.
- **Cue-timed reveals**: `data-cue="word"` makes an element appear when the narrator says it, using the voice's word timings.
- **Revisions and versions**: ask for changes in plain language for the module, one slide, or a moment in the video
  ("at 2:51"); editing the script redesigns only the changed slides; every result is a version that can be restored.
- **Script suggestions** for typos, unclear lines, risky wording and pronunciation, accepted one by one.
- **Brand kit import** (guidelines PDF, logos, font files, an existing module), a **glossary** with pronunciations and
  banned terms, and a **Settings** page for the Anthropic API key.
- `html2mp4-script` command, a project store under `~/Downloads/Narrated Videos/Modules`, and a pytest suite.

### Changed
- The Studio opens on the Write page. The front end is split into separate files.
- Pronunciations change what the voice says without changing captions or slides.

## [0.3.0] - 2026-10-13

### Added
- **Preview 10 s** in the Studio, and `--preview SECONDS` on the command line, to audition voice, pace and music
  before rendering a whole module.
- Music volume levels (`subtle`, `balanced`, `present`), replacing the fixed level.
- Output quality choice: 1440p (new default) or 1080p.
- Cancelling queued or running jobs from the Studio. Cancellation takes effect at the next sentence or frame.
- The Studio reconnects to work in progress after a page reload, and a waiting job names what it's waiting for.

### Changed
- Previews and full videos run in separate lanes. A full video pauses its frame workers while a preview is made, and
  runs at lower OS priority.
- The music is high-passed at 140 Hz under narration, so it stays audible on laptop speakers.
- Encoding uses a Lanczos 4:2:0 conversion with x264 CRF 17 and `tune animation`, measured within about 0.5 dB of
  lossless at about 3 MB per minute.
- Visual cues start exactly with their sentence, as in a module's own player. Previously they started 0.15 s early.
- The picture now holds on the final slide instead of fading to black. Only the sound fades.
- The render cache is keyed by file content, so re-uploading a module reuses earlier work.
- Encoder threads are shared fairly between render workers, and the voice engine uses at most four threads.

### Fixed
- Videos were rendered at 1280×720 instead of the requested resolution. Frames are now captured at the full device
  scale, and a render stops if a frame has the wrong size.

## [0.2.0] - 2026-10-13

### Added
- The Studio: a local web app to upload a module, preview voices and music, follow progress, and play and download results.
- `setup.sh`, which installs Python, dependencies, Chromium and the voice model with no admin rights or Homebrew.
- **Install.command** and **Open Studio.command** for double-click use on macOS.
- A bundled FFmpeg build through imageio-ffmpeg. A system FFmpeg is used if present.
- A getting-started guide for non-technical users.

## [0.1.0] - 2026-10-13

### Added
- `html2mp4` command: converts a narrated HTML module to MP4 with Kokoro narration, frame-exact animation through
  paused and seeked CSS transitions, parallel rendering, EBU R128 loudness normalisation, a ducked music bed, and
  embedded and sidecar captions.
- Three synthesised, royalty-free music beds.
- Example module.

[Unreleased]: https://github.com/akash-adhikary/narrated-slides-to-video/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/akash-adhikary/narrated-slides-to-video/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/akash-adhikary/narrated-slides-to-video/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/akash-adhikary/narrated-slides-to-video/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/akash-adhikary/narrated-slides-to-video/releases/tag/v0.1.0
