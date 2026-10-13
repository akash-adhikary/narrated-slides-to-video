# Troubleshooting

## Installation

**"The git command requires the command line developer tools."**
Click **Install** in the dialog, wait for it to finish, then run the setup command again.

**`zsh: permission denied: ./setup.sh`**
The scripts lost their executable bit, which can happen when the folder is copied from a ZIP. Run the following, then
try again:

```bash
chmod +x *.sh *.command
```

**Setup stops partway with a network error.**
Check your connection and run `./setup.sh` again. It skips anything already installed.

**Setup fails while installing `torch` on an Intel Mac.**
Intel Macs aren't supported. See [Requirements](../README.md#requirements).

## Opening the Studio

**macOS says "Open Studio.command" can't be opened.**
This only happens the first time. Open  › **System Settings** › **Privacy & Security**, scroll down to the message
about the file, and click **Open Anyway**.

**The browser says it can't connect to 127.0.0.1.**
The Studio isn't running. Double-click **Open Studio.command** again and keep its Terminal window open.

**"The app isn't installed yet."**
`setup.sh` hasn't completed in this folder. Run `./setup.sh`.

## Making videos

**"This file doesn't contain a narration script."**
The file isn't a narrated slide module, or it's a different version without the `scenes` list. See
[Authoring modules](authoring.md).

**"The script mentions slide(s) …, but the page has no element with that id."**
A scene in the narration list doesn't match any `<section>` on the page. Fix the `id` in the file.

**A preview or video says it's waiting.**
It names the job it's waiting for. Previews never wait behind a full video: the video pauses briefly instead. Use
**Cancel** on anything you no longer need.

**It's much slower than expected.**
Other heavy apps compete for the CPU, and rendering uses every core. Quit them, or choose *Faster · 1080p*. The first
video after setup is also slower, because the voice model loads and the music is prepared.

**The narrator mispronounces a word.**
The text is read literally. Change it in the module, for example spell an abbreviation out, then preview again. Only
changed sentences are re-voiced.

**The fonts in the video don't match the browser.**
Web fonts load while rendering, so the computer needs an internet connection. Alternatively, embed the fonts in the
module.

**I can't hear the background music.**
Choose *Present* under **Music volume**. The music always sits below the narrator and dips further while they speak.
On very small speakers, *Balanced* can be subtle.

## Where things are

| What | Where |
|---|---|
| Finished videos (Studio) | `~/Downloads/Narrated Videos` |
| Finished videos (command line) | Next to the input file, or the `-o` path |
| Caches and Studio history | `~/.cache/html2mp4` (safe to delete) |
| The app itself | The folder you cloned, e.g. `~/Downloads/narrated-slides-to-video` |

## Uninstalling

Delete the cloned folder and `~/.cache/html2mp4`. Setup also leaves these in your home folder, which you can remove
if nothing else uses them:

- the Chromium download in `~/Library/Caches/ms-playwright`;
- the voice model in `~/.cache/huggingface`;
- `uv`, in `~/.local/bin`.

## Reporting a problem

[Open an issue](https://github.com/akash-adhikary/narrated-slides-to-video/issues/new/choose). Include:

- your macOS version and chip;
- whether you used the Studio or the command line;
- the text from the Terminal window.

If you can share it, attach the module or a cut-down copy that shows the problem.
