"""Parse the structured script format into a module outline.

    Title: Giving Feedback That Lands
    Subtitle: Manager Essentials · Module 2
    Say: Welcome to module two.            <- optional: narration for the title slide

    ## Why feedback matters                <- a slide
    Show: Builds trust · Speeds growth     <- optional on-screen points (or "- point" lines)
    Note: use three icons                  <- optional design hint for the slide designer
    Say: Feedback is how teams get better. <- one narration step; elements can appear with it
    Say: Done well, it builds trust.

Narration is kept exactly as written. Lines starting with // are comments. A line that doesn't start with a
marker continues the previous Say:, Show: or Note:.
"""
import dataclasses, re


class ScriptError(ValueError):
    """The script can't be used; the message names the line and the fix."""


@dataclasses.dataclass
class Slide:
    title: str
    say: list = dataclasses.field(default_factory=list)
    show: list = dataclasses.field(default_factory=list)
    note: str = ""


@dataclasses.dataclass
class Module:
    title: str
    subtitle: str = ""
    intro: list = dataclasses.field(default_factory=list)     # narration for the title slide
    slides: list = dataclasses.field(default_factory=list)

    @property
    def sentences(self): return len(self.intro) + sum(len(s.say) for s in self.slides)

    @property
    def words(self): return sum(len(t.split()) for t in self.intro + [x for s in self.slides for x in s.say])

    def to_dict(self): return dataclasses.asdict(self)


MARKER = re.compile(r"^(title|subtitle|say|show|note)\s*:\s*(.*)$", re.I)
SPLIT_SHOW = re.compile(r"\s*[·•|;]\s*")


def parse(text, title=None, subtitle=None):
    """Parse a script. `title`/`subtitle` (e.g. from a CSV column) override the script's own."""
    m = Module(title="", subtitle="")
    slide, last = None, None            # last = (kind, target) for continuation lines
    for n, raw in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("//"):
            last = None if not line else last
            continue
        if line.startswith("## "):
            slide = Slide(title=line[3:].strip()); m.slides.append(slide); last = None
            if not slide.title: raise ScriptError(f"Line {n}: a slide heading needs a title after '##'.")
            continue
        if line.startswith("# ") and not m.slides and not m.title:
            m.title = line[2:].strip(); last = None; continue
        if line.startswith(("- ", "* ")):
            if slide is None: raise ScriptError(f"Line {n}: on-screen points belong under a '## Slide title'.")
            slide.show.append(line[2:].strip()); last = ("show", slide); continue
        mk = MARKER.match(line)
        if mk:
            kind, value = mk.group(1).lower(), mk.group(2).strip()
            if kind in ("title", "subtitle"):
                if slide is not None: raise ScriptError(f"Line {n}: '{kind.title()}:' goes at the top, before the first slide.")
                setattr(m, kind, value); last = None; continue
            if kind == "say":
                if not value: raise ScriptError(f"Line {n}: 'Say:' has no text.")
                (slide.say if slide else m.intro).append(value); last = ("say", slide); continue
            if slide is None: raise ScriptError(f"Line {n}: '{kind.title()}:' belongs under a '## Slide title'.")
            if kind == "show":
                slide.show += [p for p in SPLIT_SHOW.split(value) if p]; last = ("show", slide)
            else:
                slide.note = (slide.note + " " + value).strip(); last = ("note", slide)
            continue
        # continuation of the previous field
        if last is None:
            raise ScriptError(f"Line {n}: not sure what this is: “{line[:60]}”. Start it with 'Say:', 'Show:', 'Note:' or '## '.")
        kind, target = last
        if kind == "say":
            lst = target.say if target else m.intro
            lst[-1] = f"{lst[-1]} {line}"
        elif kind == "show":
            target.show[-1] = f"{target.show[-1]} {line}"
        else:
            target.note = f"{target.note} {line}"

    if title: m.title = title.strip()
    if subtitle: m.subtitle = subtitle.strip()
    if not m.title: raise ScriptError("The script needs a title: add 'Title: …' as the first line.")
    if not m.slides: raise ScriptError("The script has no slides: start each slide with '## Slide title'.")
    for s in m.slides:
        if not s.say: raise ScriptError(f"Slide “{s.title}” has no narration: add at least one 'Say:' line.")
    return m


EXAMPLE = """Title: Giving Feedback That Lands
Subtitle: Manager Essentials · Module 2
Say: Welcome to module two of Manager Essentials.

## Why feedback matters
Show: Builds trust · Speeds up growth · Prevents surprises
Say: Feedback is how good teams get better.
Say: Done well, it builds trust, speeds up growth, and prevents surprises at review time.

## The SBI model
Show: Situation · Behavior · Impact
Note: three steps, left to right
Say: A simple structure helps: situation, behavior, and impact.
Say: Describe when it happened, what the person did, and the effect it had.

## Your next step
Show: Pick one piece of feedback you've been holding back
Say: Before your next one-to-one, pick one piece of feedback you've been holding back.
Say: Write it down using situation, behavior, and impact, and share it this week.
"""
