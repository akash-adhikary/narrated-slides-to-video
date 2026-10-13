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
  and voices from Hugging Face, and whatever the module itself loads, such as web fonts.
- **Modules are executed.** Converting a module runs its HTML and JavaScript in headless Chromium, just as opening
  it in a browser would. Only convert modules from sources you trust.
