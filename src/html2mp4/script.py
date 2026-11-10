"""Parse the structured script format into a module outline.

    Title: Giving Feedback That Lands
    Subtitle: Manager Essentials · Module 2
    Say: Welcome to module two.            <- optional: narration for the title slide

    ## Why feedback matters                <- a slide
    Show: Builds trust · Speeds growth     <- optional on-screen points (or "- point" lines)
    Note: use three icons                  <- optional design hint for the slide designer
    Hold: 3                                <- optional: seconds the finished slide stays up after its last sentence
    Say: Feedback is how teams get better. <- one narration step; elements can appear with it
    Say: Done well, it builds trust.

Narration is kept exactly as written. Lines starting with // are comments. A line that doesn't start with a
marker continues the previous Say:, Show: or Note:.

A second, more natural format is also accepted (detected by its "Scene N:" lines):

    One micro-learning: How to Interview Candidates      <- the first line is the title
    Scene 1: The opening (0:00 to 0:30)
    On screen: "Every hire shapes the team."             <- what should be shown (a description, not exact text)
    Think back to the best colleague you've worked with. What made them the best?   <- narration paragraph

Each narration paragraph is split into sentences, one narration step each.
"""
import dataclasses, re


class ScriptError(ValueError):
    """The script can't be used; the message names the line and the fix."""


@dataclasses.dataclass
class Slide:
    title: str
    say: list = dataclasses.field(default_factory=list)
    show: list = dataclasses.field(default_factory=list)   # exact on-screen points (Show: / bullets)
    note: str = ""                                          # a design hint
    screen: str = ""                                        # the author's description of what appears ("On screen:")
    timing: str = ""                                        # the author's intended window, e.g. "0:30 to 1:30"
    hold: float | None = None                               # extra seconds the finished slide stays up (None: the Studio's pacing setting)


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


MARKER = re.compile(r"^(title|subtitle|say|show|note|hold)\s*:\s*(.*)$", re.I)
MAX_HOLD = 30.0


def parse_hold(value, n):
    """'Hold: 3', '3s' or '2.5 seconds' -> seconds."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:s|sec|secs|second|seconds)?", value.strip(), re.I)
    if not m: raise ScriptError(f"Line {n}: 'Hold:' needs a number of seconds, like 'Hold: 3'.")
    seconds = float(m.group(1))
    if seconds > MAX_HOLD: raise ScriptError(f"Line {n}: 'Hold:' can be at most {MAX_HOLD:g} seconds.")
    return seconds
SCENE = re.compile(r"^scene\s+(\d+)\s*[:.\-–—]\s*(.*?)\s*(?:\(([^)]*\d:\d\d[^)]*)\))?\s*$", re.I)
NARRATION = re.compile(r"^(?:narration|narrator|voice[- ]?over|vo|script|says?)\s*:\s*(.*)$", re.I)
QUOTES = ('"', '“', '”')


def _unquote(text):
    """A narration written in quotes ("Quick challenge. …") is the words without them, so it splits into sentences."""
    t = text.strip()
    if len(t) > 1 and t[0] in QUOTES and t[-1] in QUOTES and sum(t.count(q) for q in QUOTES) == 2: return t[1:-1].strip()
    if t[:1] in QUOTES and sum(t.count(q) for q in QUOTES) == 1: return t[1:].strip()          # an opening quote, closed on a later line
    if t[-1:] in QUOTES and sum(t.count(q) for q in QUOTES) == 1: return t[:-1].strip()
    return t


ON_SCREEN = re.compile(r"^(?:on[- ]screen(?: text)?|screen|visual)\s*:\s*(.*)$", re.I)
ABBREVIATIONS = ("e.g.", "i.e.", "vs.", "etc.", "mr.", "mrs.", "ms.", "dr.", "inc.", "approx.", "no.", "st.")


def split_sentences(text):
    """Split a paragraph into sentences without breaking inside quotes or after abbreviations."""
    text = " ".join(text.split())
    pieces = re.split(r"(?<=[.!?])(?<![0-9]\.)([\"”’')]?)\s+(?=[A-Z“\"‘(])", text)
    # re.split with one group alternates text, captured closing mark, text, ...
    parts, i = [], 0
    while i < len(pieces):
        piece = pieces[i] + (pieces[i + 1] if i + 1 < len(pieces) else "")
        i += 2
        parts.append(piece)
    out = []
    for part in parts:
        if out:
            prev = out[-1]
            open_quote = prev.count("“") > prev.count("”") or prev.count('"') % 2 == 1
            last_word = prev.split()[-1].lower() if prev.split() else ""
            if open_quote or last_word in ABBREVIATIONS:
                out[-1] = f"{prev} {part}"; continue
        out.append(part)
    return [x.strip() for x in out if x.strip()]


def _quoted(text):
    """Quoted phrases in a description, e.g. “Every hire shapes the team.” (curly or straight quotes)."""
    return [q.strip() for q in re.findall(r"[“\"]([^”\"]{2,120})[”\"]", text)]
SPLIT_SHOW = re.compile(r"\s*[·•|;]\s*")


def parse(text, title=None, subtitle=None):
    """Parse a script. `title`/`subtitle` (e.g. from a CSV column) override the script's own."""
    if any(SCENE.match(l.strip()) for l in text.splitlines()):
        return _parse_scenes(text, title, subtitle)
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
            if kind == "hold":
                slide.hold = parse_hold(value, n); last = None
            elif kind == "show":
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


def _parse_scenes(text, title, subtitle):
    m = Module(title="", subtitle="")
    slide, head, in_screen = None, [], False
    for n, raw in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("//"):
            in_screen = False if not line else in_screen
            continue
        sc = SCENE.match(line)
        if sc:
            slide = Slide(title=sc.group(2).strip() or f"Scene {sc.group(1)}", timing=(sc.group(3) or "").replace("–", "to").strip())
            m.slides.append(slide); in_screen = False
            continue
        if slide is None:
            head.append(line); continue
        os_ = ON_SCREEN.match(line)
        if os_:
            slide.screen = os_.group(1).strip(); in_screen = True; continue
        mk = MARKER.match(line)
        if mk and mk.group(1).lower() == "note":
            slide.note = (slide.note + " " + mk.group(2)).strip(); in_screen = False; continue
        if mk and mk.group(1).lower() == "hold":
            slide.hold = parse_hold(mk.group(2), n); in_screen = False; continue
        if in_screen and not slide.say and line.endswith((":",)) is False and len(line) < 200 and not re.search(r"[.!?]\s+[A-Z]", line):
            slide.screen = f"{slide.screen} {line}".strip(); continue      # a wrapped On screen: description
        in_screen = False
        nar = NARRATION.match(line)
        if nar: line = nar.group(1)                                     # "Narration: …" labels what is said; it isn't said itself
        line = _unquote(line)
        if line: slide.say += split_sentences(line)
    if head:
        first = head[0]
        m.title = re.sub(r"^(?:one\s+)?micro-?learning\s*[:\-–—]\s*", "", first, flags=re.I).strip()
        if len(head) > 1: m.subtitle = " ".join(head[1:])[:120]
    for s in m.slides:
        s.show = _quoted(s.screen) if s.screen and len(_quoted(s.screen)) >= 1 and len(s.screen) < 160 else []
    if title: m.title = title.strip()
    if subtitle: m.subtitle = subtitle.strip()
    if not m.title: raise ScriptError("The script needs a title: put it on the first line, before 'Scene 1:'.")
    for s in m.slides:
        if not s.say: raise ScriptError(f"Scene “{s.title}” has no narration: write what the narrator says under it.")
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
