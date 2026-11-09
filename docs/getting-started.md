# Getting started

This guide takes you from nothing installed to your first finished video. It's written for people who don't use
the command line. You'll paste three short commands, once, and after that everything happens in your browser.

**You need**

- A Mac with an Apple chip (M1, M2, M3 or M4). To check, open the Apple menu  › **About This Mac** and look for
  "Chip: Apple M…".
- About 3 GB of free disk space and an internet connection for the one-time setup.
- No admin password and no developer tools.

## 1. Install (once, about 10 minutes)

1. Open **Terminal**: press ⌘ Space, type `Terminal` and press Return.
2. Copy this line, paste it into Terminal with ⌘ V, and press Return:

   ```bash
   cd ~/Downloads && git clone https://github.com/akash-adhikary/narrated-slides-to-video.git && cd narrated-slides-to-video && ./setup.sh
   ```

3. Wait until you see **All set.** The last step downloads the narrator voice and can take a few minutes.

If macOS shows a dialog saying the `git` command needs the command line developer tools, click **Install**. Wait for
it to finish, then paste the line from step 2 again.

The Studio is now installed in **Downloads › narrated-slides-to-video**. Don't move or rename this folder.

## 2. Open the Studio

In Finder, open **Downloads › narrated-slides-to-video** and double-click **Open Studio.command**. The Studio opens in
your web browser, and a small Terminal window opens alongside it. Keep that window open while you work and close it
when you're done.

**The first time only**, macOS may refuse to open the file because it comes from an unidentified developer. Click
**Done**, then open  › **System Settings** › **Privacy & Security**. Scroll down to the message about
"Open Studio.command" and click **Open Anyway**.

If you prefer Terminal, this does the same thing:

```bash
cd ~/Downloads/narrated-slides-to-video && ./studio.sh
```

## 3. Write your script

The Studio opens on the **Write** page.

1. Paste your script into the box, or click **Insert an example** to see the format. The line under the box tells you
   how many slides it found, or what's wrong and on which line.
2. Optional: click **Check my script** for suggestions on typos, unclear lines and risky wording. Nothing changes unless
   you accept it.
3. Click **Design slides**. This takes 4 to 8 minutes and about $1 of Claude usage. You can leave the page.
4. Review the slides. Step through them, and describe any change in the box underneath, for example
   "make the cards on slide 4 larger" or "at 2:51 the boxes overlap". Only the slides you name change, and every change is
   saved as a version you can go back to.
5. Click **Use these slides to make the video**.

You'll need an Anthropic API key for step 3: open **Settings**, paste it under *Anthropic API key*, and click
*Save and verify*. No key? **Quick layout** builds a simple version without AI. Already have an HTML module? Skip to the
next part and upload it on the Create video page.

Before your first script, you can also import your company's brand in **Settings › Brand kit**: drop in the brand folder
or guidelines PDF, review what was found, and click *Apply*. Slides will then use your colours, fonts and logo.

More detail: [From script to slides](scripts.md).

## 4. Make a video

1. **Your module.** If you came from the Write page it's already here. Otherwise drag your `.html` file onto the page, or click *browse your computer*. You'll see its title, the
   number of slides and the approximate length. Open *Read the narration script* to check the wording.
2. **Narrator.** Press ▶ to hear a voice, and click one to choose it. Set the pace to Relaxed, Natural or Brisk.
3. **Background music.** Press ▶ to preview a track, or choose *No music*. *Music volume* sets how noticeable it is.
   The music always dips while the narrator speaks. You can also upload your own royalty-free track.
4. **Video quality.** *Sharpest · 1440p* is recommended. *Faster · 1080p* takes less time to make.
5. **Preview.** Click **Preview 10 s** to hear the opening with your choices. It takes about half a minute. Change
   anything you like and preview again.
6. **Create video.** A 2–3 minute module takes 5–8 minutes. You can keep using your Mac in the meantime.

When it's done, the video plays on the page. **Download video** saves a copy. Every video is also saved automatically
to **Downloads › Narrated Videos**, alongside two caption files:

- `.srt` and `.vtt` are captions for your learning platform. Most platforms accept either.
- The captions are also inside the MP4, so viewers can switch them on with the CC button. They're never burned into
  the picture.

## Good to know

- **Closing the tab doesn't stop anything.** A video keeps being made while the Studio is running. Open it again to
  see the progress, or click **Cancel** to stop.
- **The narrator reads the script exactly as written.** If a word is wrong or mispronounced, it has to be fixed in
  the `.html` file. Abbreviations work best spelled the way they're said, for example "S Q L".
- **Your files stay on your Mac.** Making a video uploads nothing. When you design slides, check a script or import a
  brand guidelines PDF, the text is sent to Anthropic (the company behind Claude) to do that work. The internet is also
  used during setup and to load any web fonts a module uses.

## Updating

To get the latest version, run this in Terminal:

```bash
cd ~/Downloads/narrated-slides-to-video && git pull && ./setup.sh
```

## If something goes wrong

See [Troubleshooting](troubleshooting.md). If you're still stuck, send a screenshot of the Terminal window to whoever
shared the Studio with you.
