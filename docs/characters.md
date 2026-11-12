# Characters: a mascot that talks and acts

A character is a picture-in-motion that speaks in its own voice, moves its mouth only on its own lines, and does things on cue
("Spotter animate: wave"). The script words are in [From script to slides](scripts.md#a-character-that-talks-and-acts-spotter). This page is
about making one.

## What a character is made of

| Part | What it is | Where it comes from |
|---|---|---|
| **Idle loop** | Always playing: blinking, ears, tail | A quiet moment of a clip |
| **Talking loop** | The same, with the mouth working. Shown only while it speaks | The part of a clip where it speaks |
| **Actions** | Wave, wink, laugh, think… each a short clip | Parts of clips, named by you |
| **Motions** | Jump, hop, nod, shake, bounce, wiggle, spin | Built in: no clip needed |
| **Voice** | What it sounds like | Settings, per character |

Everything is cut from clips of the same character filmed the same way, so the picture never shifts when it switches from idle to talking
to an action.

## Making Spotter's clips with an AI video tool

Any AI video tool that animates a picture works (Gemini, Runway, Kling, Luma, Hailuo…). Free tiers allow only a few clips a day, so make each
clip count: **one clip can hold several actions** one after another, and you cut them apart afterwards. Two clips are enough to start:

1. **A start picture.** A picture of the character standing, full body, on a flat bright green background, in a wide (16:9) frame with
   room around it. If you only have a picture on white, ask an image tool: *"Same character, same style, on a perfectly flat solid
   chroma-key green screen, no floor, no shadow, wide 16:9 frame, filling about 65% of the height."*
2. **A talking clip.** Prompt: *"Animate this exact character, keeping his design identical. Static locked camera, no zoom, no cuts. The
   background stays a perfectly flat solid green screen the whole time: no floor, no shadows, no objects. He stays in the same spot. For
   the first second he stands relaxed with a warm closed-mouth smile, blinking once. Then he talks to the camera in a cheerful voice,
   saying: "…a sentence or two…". His mouth moves naturally and continuously until the end."* The quiet start becomes the idle loop;
   the talking becomes the talking loop. (Its sound is only used to find when he speaks.)
3. **An expressions clip.** Prompt: *"…same setup, no speech. In about ten seconds he does four short actions one after another, relaxing
   in the starting pose between them: first, at about 1 second, he waves hello with one paw; second, at about 3.5 seconds, he laughs out
   loud, head back; third, at about 6 seconds, he tilts his head and raises a paw to his chin as if thinking; fourth, at about 8.5 seconds,
   he wags his tail excitedly."*

Keep the same start picture for every clip, and tell the tool *"static camera"* and *"stays in the same spot"*: that is what makes the clips
line up. If a tool will not hold the green steady, try again or use a white background (it works, but cutting out each frame is slower).

## Putting it in the Studio

1. **Settings > Media library > Upload**: add the talking clip (MP4 or MOV).
2. Open it and choose **Make a talking character**. The green screen is removed (fast, with soft fur edges and the green taken out of the
   colours), then the idle and talking loops are made. Give the new character a **name** and set **Speaks as** to the name scripts will use
   (for example `Spotter`). Choose its **Voice**.
3. Upload the expressions clip. Open it, and for each action choose the character, type the action's **name** (`wave`), and the seconds it
   spans if it is only part of the clip, then **Add as action**. Each is cut out in exactly the same frame as the character.
4. In a script, write `Spotter say: …` and `Spotter animate: wave`. Slides place him automatically.

The assistant knows what each character can do, so you can ask it: *"add Spotter waving at the start and a wink after the second slide's
last line."*

## Sharing a character

Open the character in **Settings > Media library** and choose **Export this character as a file**. You get one small `.zip` (Spotter's is
about 8 MB) holding the character, his action clips, the cut-out they were made from (so new actions can still be matched to him) and his
voice setting. On another computer, **Settings > Media library > Import a character** brings it all in. Importing never overwrites: if the
name is taken the copy is called "Spotter (2)", and you are told when two characters speak as the same name. The original green-screen films
are not included, and the file is a mascot, so share it only with people who should have it.

## Good to know

- **The slide designer places the character** (large, on its own side, at the bottom of the slide) and leaves room for his jumps. A slide
  check reports when he is missing from a slide where he speaks, or when a line meant to be voice-only was printed on the slide.
- **Size.** A character is stored once in the module page however many slides use it, and each slide carries only the clips it plays.
  Spotter's pack adds roughly 3 MB to a module that uses a few actions.
- **Privacy.** Uploading your mascot to an outside AI service is a brand and legal decision. Company accounts (such as a company Gemini
  or ChatGPT) usually do not train on uploads; check yours first.
- **Voices** are made on this computer. A character's voice is a narrator voice lifted a few semitones, which is why it sounds younger.
  More Kokoro voices can be used by name (`Voice: Spotter = Sky`); each downloads once, about half a megabyte, the first time it is used.
