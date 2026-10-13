# Getting started with Narrated Slides Studio

Narrated Slides Studio turns a narrated slide module (an `.html` file) into a polished video, with a voiceover,
background music and captions. Everything happens on your own Mac and nothing is uploaded anywhere.

You need:

- a **Mac with an Apple chip** (M1, M2, M3 or M4). To check, click the Apple menu  → *About This Mac*: it says "Chip: Apple M…"
- about **3 GB of free space** and an internet connection for the one-time setup
- **no admin password** and no technical knowledge

---

## Part 1: One-time setup (about 10 minutes)

### Step 1: Open Terminal

Press **⌘ Command + Space**, type **Terminal**, and press **Return**. A window with a text prompt opens.

> Terminal is just a place to type instructions. Copy each block below, paste it into Terminal with
> **⌘ Command + V**, and press **Return**.

### Step 2: Make a folder and download the Studio

Copy and paste these lines all at once, then press **Return**:

```bash
mkdir -p ~/Downloads/narrated-video
cd ~/Downloads/narrated-video
git clone https://github.com/akash-adhikary/narrated-slides-to-video.git
cd narrated-slides-to-video
```

- If a box pops up saying the **"git" command requires the command line developer tools**, click **Install**, wait
  for it to finish, then paste the lines above again.
- If it asks for a **GitHub username and password**, you haven't been given access yet. Ask the person who shared
  this guide.

### Step 3: Install

Paste this and press **Return**:

```bash
./setup.sh
```

You'll see four steps tick by. The last one downloads the narrator voice and can take a few minutes. When you see
**All set! 🎬**, setup is done. You never need to do Part 1 again.

---

## Part 2: Making a video (every time)

### Open the Studio

Either:

- **Double-click "Open Studio.command"** in the `Downloads › narrated-video › narrated-slides-to-video` folder, or
- in Terminal, paste:

  ```bash
  cd ~/Downloads/narrated-video/narrated-slides-to-video && ./studio.sh
  ```

The Studio opens in your web browser. **Leave the Terminal window open** while you use it, and close it when you're done.

> **The first time you double-click "Open Studio.command"**, macOS may say it "cannot be opened" or "cannot
> verify the developer". Click **Done**, open  → **System Settings** → **Privacy & Security**, scroll down and click
> **Open Anyway** next to the message about "Open Studio.command". You only need to do this once.

### Create your video

1. **Your module.** Drag your `.html` file onto the page, or click *browse your computer*. You'll see the title,
   number of slides and roughly how long the video will be. Click *Read the narration script* to check the wording.
2. **Narrator.** Press ▶ to hear each voice and click the one you like. Choose a pace: *Relaxed*, *Natural* or *Brisk*.
3. **Background music.** Press ▶ to preview. The music automatically gets quieter whenever the narrator speaks.
   Choose how noticeable it is (*Subtle*, *Balanced* or *Present*), choose *No music*, or upload your own royalty-free track.
4. **Video quality.** Leave it on *Sharpest · 1440p* (crisp text, still a small file). *Faster · 1080p* is quicker to make.
5. **Try it first.** Click **Preview 10 s** to hear the first 10 seconds with your choices. It takes about half a minute.
   Change anything and preview again until you're happy.
6. Click **Create video**. A 2–3 minute module takes about 5–8 minutes. You can use other apps meanwhile.

When it's done, the video plays right on the page. Click **Download video**, or **Show in folder**. Every video is
also saved automatically in **Downloads › Narrated Videos**, together with two caption files:

- **`.srt`** and **`.vtt`** are captions for your learning platform (LMS), YouTube, etc. Most platforms accept either.
- The captions are also *inside* the MP4. Viewers can turn them on or off with the **CC** button in their video player.
  They are never burned into the picture.

---

## Good to know

- **Wording.** The narrator reads the script exactly as written, so the script must be correct in the HTML file itself.
  If a name or abbreviation sounds wrong, ask the module's author to spell it the way it's said (e.g. "S Q L").
- **Closed the tab or refreshed?** Nothing is lost. The video keeps being made, and reopening the page shows its progress.
  Use **Cancel** to stop it.
- **Changing just the music** of a video you already made is quick (under a minute), because the Studio remembers
  the animation it already drew.
- **Privacy.** Your files are processed on your Mac only. The internet is used only during setup and to load any
  web fonts the module uses.

## Something went wrong?

| What you see | What to do |
|---|---|
| "This file doesn't contain a narration script…" | The file isn't a narrated slide module. Check you picked the right `.html` file. |
| The browser page says it can't connect | The Studio isn't running. Double-click **Open Studio.command** again and keep its window open. |
| `zsh: permission denied: ./setup.sh` | Paste `chmod +x *.sh *.command` and press Return, then try again. |
| Setup stopped with an error | Check your internet connection and run `./setup.sh` again. It continues where it left off. |
| Anything else | Copy the text from the Terminal window and send it to the person who shared this guide. |

## Updating to a newer version

```bash
cd ~/Downloads/narrated-video/narrated-slides-to-video && git pull && ./setup.sh
```
