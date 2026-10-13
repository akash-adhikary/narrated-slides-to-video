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

## 3. Make a video

1. **Your module.** Drag your `.html` file onto the page, or click *browse your computer*. You'll see its title, the
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
- **Your files stay on your Mac.** Nothing is uploaded. The internet is only used during setup and to load any web
  fonts the module uses.

## Updating

To get the latest version, run this in Terminal:

```bash
cd ~/Downloads/narrated-slides-to-video && git pull && ./setup.sh
```

## If something goes wrong

See [Troubleshooting](troubleshooting.md). If you're still stuck, send a screenshot of the Terminal window to whoever
shared the Studio with you.
