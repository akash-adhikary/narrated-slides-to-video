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

## Writing and designing

**"Designing slides needs an Anthropic API key."**
Open **Settings**, paste your key under *Anthropic API key* and click *Save and verify*. You can also use **Quick layout**
on the Write page, which needs no key.

**"Anthropic didn't accept that key."**
Check it was copied completely (it starts with `sk-ant-`). A key saved in Settings takes priority over one set in your
environment.

**The script box says "Line N: not sure what this is".**
A line doesn't start with a marker. In the Say/Show format, lines begin with `Say:`, `Show:`, `Note:` or `## `. See
[From script to slides](scripts.md#writing-a-script).

**The design takes a long time.**
A six-slide module usually takes 2 to 4 minutes (4 to 5 with *Thorough* design quality): most of it is Claude composing the layouts. It carries on if you leave
the page. If it stays stuck, check your internet connection.

**The checker still lists a problem after the fix rounds.**
Two rounds of automatic fixes is the limit. Describe the change you want in *Ask for a change*, naming the slide.

**A slide uses a word that isn't in my script.**
That's a note, not an error: labels are often shortened or reworded. Check it says what you mean; ask for a change if not.

**The preview looks different from my brand.**
Check **Settings › Brand kit**, then ask for the whole module to be redesigned with a note about what's off.

### The player

**There's no sound, or no voice list.** Play uses your browser's own voices. Chrome, Edge and Safari have them; some Linux
setups don't. Without a voice the player still runs, paced silently. Make sure the tab isn't muted.

**The voice sounds different from the video.** It is meant to: Play is a preview with your browser's voice. **Studio voice** (in the
Studio) plays the voice the video uses.

**Studio voice isn't there.** It only appears when the module is open inside the Studio, because the Studio makes the voice. In a
downloaded file the browser voice is used.

**Studio voice says "Preparing…" for a long time.** The first time for a script, every sentence has to be voiced: about 2 seconds
per sentence, after 10 seconds to load the voice. The button counts them ("Preparing 12/39") and a message under the video says what
is happening. Voices are made one at a time, so if a video or another preview is being made the message says it is waiting for that
to finish. Click the button again to cancel. While it prepares, Play keeps going with your browser's voice and the studio voice takes
over at the next sentence, never in the middle of one.

**"The studio voice was interrupted. Reconnecting…"** The Studio stopped answering, usually because it was restarted. The player tries
for about 10 seconds, then carries on from the same sentence. If it can't reconnect it says so and continues with your browser's voice;
press **Studio voice** to try again.

**"Your browser blocked the sound."** Some browsers refuse to start sound without a click on the page. Press Play.

**Full screen doesn't work inside the page.** Use **Open large**, or press F in the larger tab.

**I opened a file and it says it can't be edited.** Only modules made by the Studio carry their script and slide designs. Any
module file can still be turned into a video on the Create video page.

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
