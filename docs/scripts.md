# From script to slides

The **Write** page turns a script into a finished slide module (the HTML that the video is made from). You write what
the narrator says and what should be on screen. Claude designs the slides in your brand, a checker renders every step
to catch problems, and you refine the result until it's right.

This page covers the script format, how the slides are designed and checked, and how to ask for changes. For making the
video afterwards, see [Getting started](getting-started.md).

## Building the script with AI

You don't have to write the script yourself. Press the glowing **Build with AI** button at the bottom right of the Write page (or
**Build it with AI** above the script box) and talk it through with Claude:

- **Start from an idea.** Say what the video is about and who it's for. If the brief is thin, Claude asks a few short questions;
  if you say "just write it", it drafts straight away and tells you what it assumed. You can type or press the microphone to speak.
- **Keep tweaking.** Ask in plain words: "make it shorter", "make the opening more engaging", "add a recap slide", "slide 4 should be a
  comparison". Claude edits the script in the box and lists what changed. Slides you didn't ask about stay word for word the same, so
  they aren't redesigned. Anything you type into the box by hand is picked up on the next message.
- **Undo any change** from the card in the chat. Nothing is designed until you press **Design slides** (or **Update slides**).
- **Change the slides in the same conversation.** Once the slides are designed, the same chat changes them: words ("add a slide about
  follow-up questions") and looks ("make the second to last slide a timeline"), in one message. Claude lists what changes on a card with
  one **Apply to slides** button; the progress shows in the chat. Turn on **Apply changes to the slides automatically** to skip the
  button. Before the slides exist, Claude puts visual ideas in the script as `Note:` lines instead.
- **It only redoes what changed.** Claude edits just the slides it touches (so a reply takes seconds, not a rewrite of the whole script),
  and only those slides are redesigned, side by side. Adding or removing a slide in the middle doesn't redesign the ones after it: they
  keep their designs. A change to two slides typically takes 1 to 2 minutes and about $0.50.
- **Mix it with pasting.** Paste a structured script, open a file, or start from the example, and use the chat to improve it. The
  conversation is remembered per module in your browser (**New chat** clears it).

The chat uses your Anthropic API key. A reply costs a few cents; the panel shows the running total. The conversation and your
script are sent to Anthropic, as when designing slides.

## Writing a script

Two formats are accepted. The Studio detects which one you used.

### Scenes

The format most people write naturally. The first line is the title; each `Scene` is one slide.

```text
One micro-learning: How to Interview Candidates
About 6 minutes. Narration with on-screen text.

Scene 1: The opening (0:00 to 0:30)
On screen: “Every hire shapes the team.”
Think back to the best colleague you've ever worked with. What was it about them
that made you believe they were the best? Our job is to find people like that.

Scene 2: What we're looking for (0:30 to 1:30)
On screen: four labels appear in turn: Curious. Owns the work. Persevering.
Our leaders told us that strong candidates share several traits. They're curious…
```

- **The narration** is every line under a scene that isn't `On screen:` or `Note:`. It's split into sentences, and each
  sentence is one step that things can appear on.
- **`On screen:`** says what should be shown. Text in quotes is used word for word. Anything else is a description
  that Claude turns into short labels.
- **`Note:`** is an optional design hint, such as `Note: three cards, left to right`.
- The time in brackets is your intended timing. It isn't enforced; it only helps when you refer to a moment in feedback.

### Say / Show

A more explicit format, useful when you want control over each sentence and each on-screen point.

```text
Title: Giving Feedback That Lands
Subtitle: Manager Essentials · Module 2
Say: Welcome to module two.                   ← narration for the title slide

## Why feedback matters
Show: Builds trust · Speeds up growth · Prevents surprises
Say: Feedback is how good teams get better.
Say: Done well, it builds trust, speeds up growth, and prevents surprises.
```

`Show:` lists exact on-screen points, separated by `·`, or use lines starting with `- `. A line that doesn't start with a
marker continues the line above it. Lines starting with `//` are comments.

### Your narration is never rewritten

The narrator reads your sentences exactly as written. Claude only designs the visuals. If something in the script is
wrong, fix it in the script and the slides follow. Use **Check my script** to get suggestions (see below) rather than
asking for wording changes in the feedback box.

## Checking your script

**Check my script** asks Claude to look for real problems only: typos, lines a new employee wouldn't understand,
wording that could read as a promise or commitment, and words a text-to-speech voice may say wrongly. Nothing changes
unless you accept it:

- **Typos, clearer wording and careful wording** show the original and the replacement. *Accept* edits your script.
- **Pronunciation** suggestions, such as "R&D" → "R and D", go to your pronunciation list. The voice says the spoken
  form; the slides and captions keep the written form.

## Designing the slides

**Design slides** sends your script, your brand kit and the design rules to Claude. A six-slide module typically takes
2 to 4 minutes and about $0.60 of Claude usage. You can leave the page while it works.

Claude designs each slide as HTML and CSS using a small kit of building blocks, and decides what appears with which
sentence. For sentences that name several things in turn, each item appears on the word that names it
("curious… ownership… perseverance"). This uses the voice's real word timings in the video.

### What you see while it works

The progress card shows the stage (Plan, Write, Check, Fix, Review) and three live views of what Claude is doing:

- **Claude is thinking** shows a running summary of its reasoning, such as how it's sizing the cards or how it plans to
  handle a quote. It is a summary written by Claude, not a transcript.
- **What's happening** lists each step with a time: which slide Claude has started and how it plans to lay it out, what the
  checker found (the actual problems, in plain words), which slides are being fixed, and what the design review said.
- **Time left** is only shown once it can be estimated. While Claude is planning the layouts (usually 1 to 3 minutes) nothing
  can be measured, so the card says so rather than guessing.

**Design quality** in Settings chooses how much care Claude takes. *Balanced* (the default) takes 2 to 4 minutes for six slides
and costs about $0.60. *Thorough* takes 4 to 5 minutes and about $0.90, and tends to add more illustration and detail.

### Motion and layouts

Slides are designed to move like a video, not a slide deck. Claude draws on a fixed motion kit, so what you see in the review
player is what the video shows:

- **Entrances**: things rise, pop, slide in from a side, zoom, blur in or wipe across, on the word that names them.
- **Drawing**: icons, outlines, underlines, diagram lines and arrows trace themselves in. Numbers can count up.
- **Emphasis and flow**: a highlight sweeps under a key phrase, a card glows as it appears, and arrows appear between steps.
- **Ambient motion**: illustrations float gently, a ring or badge breathes, dashes travel along a path to show direction, and a soft
  light drifts behind every slide.

Claude also chooses from a catalogue of layouts (big statement with an illustration, flow, timeline, cycle, hub and spoke, this
versus that, stat callout, quote, checklist, levels, spotlight, cards) and varies them across the module. If you'd like a plainer
look, set **Settings > Motion** to *Calm*: entrances and slide changes only, nothing that loops. You can still ask for more or less
in the feedback box, for example "make slide 3 a flow instead of cards".

### The checker

Before you see anything, every narration step of every slide is rendered in a browser and measured. Anything that fails
goes back to Claude with a screenshot, for up to two rounds of fixes:

| Check | What it catches |
|---|---|
| Fit | Text that spills out of its box or is cut off |
| Overlap | Text or boxes that cover each other at any step |
| Bounds | Content outside the slide margins or over the footer |
| Type scale | Any font size outside the fixed scale (96, 64, 44, 28, 22, 16 px), so every slide looks uniform |
| Contrast | Text that is hard to read against its background (4.5:1, or 3:1 for large text) |
| Rules | Scripts, outside links, images, animation, or banned terms in a design |
| Narration | Slides that don't show anything with their first sentence, or cues that aren't in the sentence |
| Wording | On-screen words that don't appear in your script. This is a note, not an error, because labels are often shortened |

A design review then looks at screenshots of the finished slides for hierarchy, spacing, alignment and brand-rule
violations, and fixes the clear defects. What remains after that is shown as notes under the preview.

### Quick layout

If you don't have an API key, or want a fast draft, **Quick layout** builds a simple, consistent module without AI:
a title, then your on-screen points as cards. It's checked the same way. You can upgrade it later with
**Design with Claude**.

## Reviewing and refining

The preview plays the module exactly as the video will show it. Use ‹ › or the slide list to step through, and click a
slide to see it fully revealed.

**Ask for a change** in plain language, for the whole module or one slide:

- "Make the cards on this slide larger."
- "Replace the checklist with four numbered cards."
- "At 2:51 the boxes overlap." Times refer to the finished video; the Studio matches them to a slide.

Only the slides you name are redesigned. Each change is checked the same way and saved as a new **version**. Pick an
earlier version from the list to look at it, and **Restore this version** to go back to it.

**Editing the script** and clicking **Update slides** redesigns only the slides whose text changed. The others stay
exactly as they were.

When you're happy, **Use these slides to make the video** moves the module to the Create video page.

## The player

The review player is part of the module file itself, so it behaves the same in the Studio and in a file you share.

- **Play** narrates with your browser's own text-to-speech voice, one sentence at a time. Choose the voice and speed (0.75× to 1.5×).
  Things appear on the words that name them. This is a *preview*: the video uses the studio voice, so timing differs slightly.
- **Studio voice** (in the Studio only) plays the same voice the video will use, with its real word timings. The first time takes
  a little while to prepare, with progress shown; after that it's instant, even after the Studio is restarted. If it's interrupted,
  the player says so, reconnects and carries on from the same sentence.
- **Full screen** (⤢, or press F; Esc to leave) hides the controls when you stop moving the mouse. **Open large** opens the player in
  its own browser tab. **CC** shows captions. Space plays and pauses, the arrow keys step, and you can click the progress bar to jump.

## Sharing a module

**Download HTML** saves the current version as one file that works offline in any browser: the fonts are embedded (the one network
request is to fetch Google Fonts the first time, if your style uses them). Send it to a colleague to review. They press Play and
hear the narration.

Two ways to use a file that comes back:

- **Open a module file (.html)** on the Write page brings it back as an editable project, with its script and slide designs, so you
  can keep refining it with Claude. If the file was changed by hand outside the Studio, you're told: later redesigns start from the
  Studio's own version of the slides, not your hand edits.
- **Create video** converts any module file exactly as it is, hand edits included.

## Your brand

Open **Settings** to set the look of every module. A fresh install starts with the bundled ThoughtSpot brand (colours, logos,
rules and the Geist fonts), so slides are on-brand straight away; importing your own kit replaces it, and Reset brings it back.

- **Brand kit.** Drop in a brand folder or `.zip`, a guidelines PDF, logos, font files, or a module you've made before.
  Claude reads the guidelines and proposes the colours, dark and light slide styles, typefaces, logos and design rules,
  which you review before anything is applied. Font files are embedded in each module, so the slides use your exact
  typefaces even offline. The module you import is kept as a style reference, so new slides match its look.
- **Words and pronunciation.** Pronunciations apply to every video. Banned terms are checked in every design.
- **Anthropic API key.** Needed to design slides, check scripts and read guidelines. It is stored only on your computer.

## What is sent to Anthropic

Designing, checking a script and reading brand guidelines send their text to Anthropic's API: the script, the brand
rules and, for style reference, a trimmed copy of one module with its images and fonts removed. Screenshots of slides
are sent for fixes and the design review. Nothing is sent when you make a video, and nothing is kept by this tool outside
your computer.

## Where things are saved

Modules are saved in `~/Downloads/Narrated Videos/Modules/<name>/`: the current `module.html`, your `script.txt`, and a
`versions/` folder with every saved version. You can open `module.html` in any browser, or convert it with
`html2mp4 module.html`.
