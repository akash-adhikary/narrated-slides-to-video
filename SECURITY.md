# Security policy

## Supported versions

Only the latest release on `main` receives fixes.

## Reporting a vulnerability

Please don't open a public issue for a security problem. Report it privately through
[GitHub's private vulnerability reporting](https://github.com/akash-adhikary/narrated-slides-to-video/security/advisories/new).
Include steps to reproduce and the impact you expect. You should get a response within a week.

## Security model

Narrated Slides Studio is designed to run on a single person's computer.

- **The Studio listens only on `127.0.0.1`.** Other machines on the network can't reach it, and it has no authentication.
- **Files stay local.** Uploaded modules, narration, music and finished videos are written to the user's cache and
  Downloads folder. Nothing is sent anywhere.
- **Network access** is limited to setup (uv, Python packages and Chromium), the first download of the voice model
  and voices from Hugging Face, whatever the module itself loads, such as web fonts, and Anthropic's API.
- **Anthropic API.** Designing slides, checking a script and reading brand guidelines send text to Anthropic: the script,
  the brand rules, a trimmed style-reference module and screenshots of slides. Nothing is sent when making a video.
  The API key is stored in `~/.config/html2mp4/settings.json`, readable only by your user account.
- **Designs are checked.** A design from Claude may not contain scripts, outside links, images, animation or event handlers;
  these are rejected before the module is saved.
- **Modules are executed.** Converting a module runs its HTML and JavaScript in headless Chromium, just as opening
  it in a browser would. Only convert modules from sources you trust.
