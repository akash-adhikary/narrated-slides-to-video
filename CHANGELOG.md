# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org).

## [Unreleased]

### Fixed
- **Remove background** on a picture with a plain backdrop (for example a white studio render) could keep the backdrop and drop the subject. The subject is now found first, and a mask that covers the backdrop along the picture's edges is never kept.
- The Create video page's progress display could be replaced by the assistant's (two scripts both defined `render`), so a video's progress didn't update. Each now has its own, and a test stops any two Studio scripts sharing a name.
- Scene-format scripts with `Narration: "…"` (or `Voiceover:`) lines: the label is no longer read aloud and quoted narration is split into sentences, instead of a whole scene becoming one long sentence. Takes effect when the module is designed again.

### Added
- **A character that talks and acts.** A library character such as the Spotter mascot is used by name in a script: `Spotter say: …` (aloud, in his own voice, never printed), `Spotter bubble: …` (aloud and printed in a speech bubble) and `Spotter animate: wave` (between two sentences: wave, wink, laugh, think, tail wag from clips of him; jump, hop, nod, shake, bounce, wiggle, spin built in). Words are matched by meaning ("wiggle his tail" finds the tail wag), an action is a beat of its own in the player and the video, and he is placed on every slide where he speaks or acts. A character has its own voice (Settings > Media library, with a Listen button): a narrator voice lifted a few semitones and quickened, which sounds younger (Puppy, Pup High, Buddy, Sunny; or `Voice: Spotter = Puppy, pitch +2`). Characters are made from clips filmed on a green screen: keyed on this computer with soft edges and the green taken out, cut in one shared frame so nothing shifts between idle, talking and an action. The slide designer, the checks and the assistant all know the new words; a slide check reports a character that is missing, a spoken line that was printed, a bubble that wasn't, and an animation he can't do. See docs/characters.md.
- **Share a character as one file.** Settings > Media library > a character > Export this character as a file makes a small `.zip` (the character, its action clips, the cut-out they came from, its voice); Import a character brings it into another library, never overwriting what is there. Imports are checked (file types, sizes, paths, only known fields). `GET /api/media/{id}/bundle`, `POST /api/media/import`.
- **Video clips in the media library.** Upload MP4, MOV or WebM (kept as WebM, silent, up to a minute); a clip on a slide plays from when the slide appears, in the player and frame-exact in the video. The library notes when a clip has speech, and **Make a talking character** turns a clip of a character speaking into a two-loop talking character (background removed per frame). Clips can also have their background removed (transparent WebM).
- **Bring a character to life.** For a mascot cut-out: Claude finds the tail, ears, tongue (or wings) and their joints, Segment Anything cuts each part out, and each moves on its own (wagging tail, floppy ears, panting tongue, breathing), with the mouth talking on top only while the narrator speaks, in the player and the video. One click in the media library, or ask the assistant; GIF downloads of the idle and talking loops. Cut-outs' soft edges no longer carry the old background's colour.
- **Media library.** Upload mascots, logos, icons and office photos once (Settings > Media library) and use them in any module with an `Image:` line, the new Insert image picker, or by asking the assistant. Uploads are cleaned (orientation, metadata such as GPS removed, size, safe SVG); Claude describes each one for the designer. Edits make new images: remove background (Claude finds the subject, Segment Anything cuts it out, on this computer), make a character talk (Claude finds the mouth; it moves only while the narrator speaks, in the player and the video), gentle float, crop, trim, square, rotate, flip, resize, convert, and download as PNG, JPG, WebP or GIF. The assistant can see attached images and edit them. Images are embedded in the module, so every export and version carries them.
- **Graphics come with the words that bring them.** A sentence that brings one graphic now shows it as the sentence starts, instead of waiting for a word partway through (on the Interviewing module the median wait went from 1.4 s to none). A sentence that names several things still shows each as it is said, now a quarter of a second early so it is readable as the word is heard. Applies to existing modules in the player and in new videos, with no redesign.
- **Time on each slide.** If a slide's last graphic goes by too quickly: add `Hold: 3` under its heading (extra seconds the finished slide stays up, 0 to 30) or choose Settings > Pacing (Standard, Comfortable +1.5 s, Relaxed +3 s) for every slide. Both apply to the preview player, downloads and videos; a `Hold:` wins over the setting; the assistant can set it ("give slide 4 more time at the end"). Timing-only edits no longer redesign slides or call Claude: the page is reassembled from the saved designs (this also fixes title-only edits redesigning every slide). CLI: `--hold SECONDS`.
- **Version history, finished.** Name a version; each version shows where it came from (icon); **Compare with current** shows changed, removed and added slides and a line diff of the script; **Take this slide back** restores a single slide with its saved design as a new version, with no Claude call; and every version has its own address (`#write/<id>/v2`) that the Back button and reloads respect. New: `PATCH /api/projects/{id}/versions/{n}`, `GET /api/projects/{id}/compare?a=N`, `POST /api/projects/{id}/restore-slide`. Names travel in module files.
- **Version control for the whole module, in the header.** The version chip next to the module name opens the history; choosing an earlier version shows that version's script *and* slides together (read-only, with a banner to go back or restore it as a new version), instead of changing only the preview. Share moved up beside it and exports the version you are viewing. A script draft you haven't designed yet is listed in the history and is waiting when you come back. `GET /api/projects/{id}?v=N` returns an earlier version whole.
- **Modules have names.** "Start a new module" asks for a name first (over a blurred page; Esc creates nothing), and the module exists from that moment: its own address (`#write/<id>`), a header with click-to-rename, a script that saves as you type, and an assistant that knows which module it is working on and keeps its conversation with the module on disk. The name (optionally numbered, e.g. `08 · Interviewing candidates`) labels lists, downloads, module files and videos; the video's title stays the `Title:` line in the script. Module files are now layout 2 (they carry the name; layout 1 files still open). Existing modules are named after their title. The old draft-before-a-module flow is gone.
- **Module file.** Share a whole module as one file: script, slide designs, the finished page, pronunciations and brand, as `.h2m.json`, with or without every version, or read the same data as YAML in the Studio. Open it on the Write page on any computer to continue editing; hand edits to the file are noticed, and files from a newer Studio are refused with a clear message. New `GET /api/projects/{id}/export`.
- The script assistant works on designed modules too: one message can change the words and the look, shown on a single card with an **Apply to slides** button (or automatic apply), with progress in the chat. Edits are slide-level patches, so replies are quick and untouched slides stay identical.
- Script assistant: a floating, glowing chat on the Write page to build a script by talking to Claude (type or speak), then keep tweaking the script and, once designed, the look of slides. It edits the script box with an undo, lists which slides changed, leaves untouched slides word for word the same, and offers Design / Update / Apply buttons instead of acting on its own. Pasting a structured script still works.
- ThoughtSpot is now the built-in brand: a fresh install starts with the ThoughtSpot colours, dark and light logos, design rules, pronunciations and the Geist / Geist Mono fonts (SIL OFL), so slides come out on-brand with no setup. Settings > Brand kit still replaces it and Reset returns to it; `HTML2MP4_BRAND=neutral` starts from the plain brand. Anyone with a saved brand is unchanged.
- **Motion and graphics.** Slides are no longer just cards. Claude now has a tested motion kit (entrances such as pop, slide, blur and
  wipe; icons, arrows and diagram lines that draw themselves in; count-up numbers; highlight sweeps and glows; arrows that appear
  between steps; gently floating illustrations and drifting light) and a catalogue of layouts to choose from (big statement with an
  illustration, flow, timeline, cycle, hub and spoke, this versus that, stat callout, quote, checklist, levels, spotlight). The design
  review flags plain boxes when the content suggests a diagram. **Settings > Motion**: Lively (default) or Calm.
- **A bigger, narrated player.** Play reads the script with your browser's own voice, with a speed control, a voice picker, captions, a
  clickable progress bar and full screen (F). Things appear on the words that name them. **Studio voice** plays the same voice the
  video will use. **Open large** opens the player in its own tab.
- **Download HTML** gives one file that works offline in any browser and carries its own script and slide designs.
  **Open a module file (.html)** on the Write page brings such a file back as an editable project (a file changed outside the Studio is
  flagged). Pronunciations in the file are added to your list if you don't have them yet.

### Fixed
- Adding or removing a slide in the middle of a designed module redesigned every slide after it. Slides are now matched by content, and unchanged ones keep their designs (with their ids moved). Changed slides are redesigned side by side instead of in one long call.
- **Studio voice could stop with no explanation.** Found by testing in the real Studio. After the Studio was restarted the player kept
  "playing" in silence. Now the voice's addresses survive a restart and anything already voiced is ready instantly; a lost voice is
  reported ("Reconnecting…") and retried for about 10 seconds before falling back, visibly, to your browser's voice; a browser that
  blocks sound pauses with a message; a sound that never starts is not waited for; the next sentence is fetched while the current one
  plays; and preparing shows real progress (loading, waiting for another voice job, sentence 12 of 39), can be cancelled, and switches at
  the next sentence instead of restarting the current one.
- Modules designed before this update had the old player (no full screen or voices). Every module is now served and downloaded with the
  current player, without touching its slides, and a refresh never makes a file look edited.
- The video renderer now handles looping animations: they run on absolute time, so every parallel render worker agrees on where
  they are and a 1-worker and a 4-worker render match.

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

- **Live view of a design in progress**: the stage (Plan, Write, Check, Fix, Review), Claude's thinking summary as it streams,
  and a timestamped feed of what's happening, including each slide's layout plan and every problem the checker finds.
  Time left is shown only once it can be estimated.
- **Design quality** setting: Balanced (the default) or Thorough.

### Changed
- **Designs are about 3× faster and cheaper** (a six-slide module: 8.4 min and $1.13 down to 2.6 min and $0.68): the first two
  slides are designed first to set the look, the rest side by side to match it; slides with problems are fixed side by side;
  a worked example in the prompt reduces first-pass mistakes; brand and reference are cached for an hour; mechanical fixes use
  a lower thinking effort; and Balanced design uses medium effort, which matched high effort in quality.
- Capitalisation, punctuation and label conventions are shared by every slide; a review problem about the whole module is fixed
  on every slide.
- The Studio opens on the Write page. The front end is split into separate files.
- Pronunciations change what the voice says without changing captions or slides.

### Fixed
- The layout checker no longer treats gradient-filled headings as boxes their own text must fit inside. That false alarm sent every
  slide through an extra fix round.

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
