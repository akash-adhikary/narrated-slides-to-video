# Contributing

Thanks for your interest in improving Narrated Slides Studio. This document covers the development setup, how the
code is organised, and what a pull request needs before it's merged.

## Development setup

```bash
git clone https://github.com/akash-adhikary/narrated-slides-to-video.git
cd narrated-slides-to-video
./setup.sh                    # creates .venv and installs the package in editable mode
source .venv/bin/activate
```

Changes to Python files take effect the next time a command runs. To run the Studio without it opening a browser
window:

```bash
HTML2MP4_NO_BROWSER=1 html2mp4-studio
```

Set `HTML2MP4_CACHE` and `HTML2MP4_OUTPUT` to scratch directories if you want to keep test runs away from your real
cache and video folder.

## Project layout

```
src/html2mp4/
  cli.py          conversion pipeline and the html2mp4 command
  studio.py       Studio server (FastAPI): uploads, job lanes, cancellation, previews, the Write page API
  music.py        music bed synthesis and the html2mp4-music command
  script.py       script formats and the parser
  compose.py      assembles a module (stage, theme, narration, review player) and the quick layout
  design.py       designs slides with Claude, then checks and fixes them
  verify.py       renders every step of every slide and measures it
  brandkit.py     reads brand folders, PDFs, logos, fonts and modules into a proposal
  review.py       script suggestions
  projects.py     saved modules and their versions
  config.py       settings: API key, brand kit, glossary
  ai.py           every call to Claude, in one place
  web/            the Studio front end (index.html, app.css, one script per page)
tests/            pytest suite
examples/         a minimal module
docs/             user and architecture documentation
setup.sh          one-step installer
studio.sh         Studio launcher (also used by the .command files)
```

[docs/how-it-works.md](docs/how-it-works.md) explains the pipeline. Read it before changing rendering, timing or audio.

## Guidelines

- **Fidelity comes first.** The video must reproduce the module's content and animation exactly. A change that alters
  what's on screen, or when it appears, needs a clear reason and an update to the
  [Fidelity](docs/how-it-works.md#fidelity) section.
- **Keep the Studio simple.** Its users aren't technical. Prefer a sensible default over a new option, and write UI
  text in plain language.
- **Keep it local.** Making a video must stay fully offline. The only network use besides setup is Anthropic's API for
  designing slides, checking scripts and reading brand guidelines, kept in `ai.py`. No telemetry or other services.
- **Match the surrounding code.** Follow its style and comment density. The front end is plain HTML, CSS and
  JavaScript, with no framework or build step.
- **Bump `RENDER_VERSION`** in `cli.py` whenever a change affects rendered frames, so caches don't serve stale pictures.

## Verifying a change

Run the automated tests first. They use a stand-in for Claude, so they're free and need no API key:

```bash
pip install -e ".[dev]" && python -m pytest
```

Then verify by hand and describe what you checked in the pull request.

1. **Command line.** Convert `examples/example.html` and a real module. Check the output with `ffprobe`: the right
   resolution, video, audio and subtitle streams, and the expected duration.
2. **Studio.** Upload, preview, create, cancel, and reload the page while a job runs.
3. **Picture.** Compare frames from the MP4 against the page in a browser at the same step, especially after
   changing rendering or timing.
4. **Sound.** Check loudness with `ffmpeg -i out.mp4 -af ebur128 -f null -`. The integrated value should be −16 LUFS.
5. **Fresh install.** For changes to `setup.sh` or dependencies, install from a clean clone with Homebrew removed from
   `PATH`.

## Pull requests

- Keep each pull request focused on one change, and explain what changed and why.
- Update the docs and add an entry under **Unreleased** in [CHANGELOG.md](CHANGELOG.md) for anything user-visible.
- Include before-and-after screenshots for Studio changes, and sample frames for rendering changes.

## Reporting bugs and requesting features

Use the [issue templates](https://github.com/akash-adhikary/narrated-slides-to-video/issues/new/choose). For security
issues, see [SECURITY.md](SECURITY.md) instead.

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
