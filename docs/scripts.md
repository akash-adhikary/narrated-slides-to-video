# From script to slides

The **Write** page turns a script into a finished slide module (the HTML that the video is made from). You write what
the narrator says and what should be on screen. Claude designs the slides in your brand, a checker renders every step
to catch problems, and you refine the result until it's right.

This page covers the script format, how the slides are designed and checked, and how to ask for changes. For making the
video afterwards, see [Getting started](getting-started.md).

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
4 to 8 minutes and about $1 of Claude usage. You can leave the page while it works.

Claude designs each slide as HTML and CSS using a small kit of building blocks, and decides what appears with which
sentence. For sentences that name several things in turn, each item appears on the word that names it
("curious… ownership… perseverance"). This uses the voice's real word timings in the video.

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

## Your brand

Open **Settings** to set the look of every module.

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
