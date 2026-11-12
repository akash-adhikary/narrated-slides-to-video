"""Parse the structured script format into a module outline.

    Title: Giving Feedback That Lands
    Subtitle: Manager Essentials · Module 2
    Say: Welcome to module two.            <- optional: narration for the title slide

    ## Why feedback matters                <- a slide
    Show: Builds trust · Speeds growth     <- optional on-screen points (or "- point" lines)
    Note: use three icons                  <- optional design hint for the slide designer
    Hold: 3                                <- optional: seconds the finished slide stays up after its last sentence
    Image: Spotter dog (talking)           <- optional: an image from the media library to show on this slide
    Say: Feedback is how teams get better. <- one narration step; elements can appear with it
    Say: Done well, it builds trust.
    Voice: Spotter = Puck                  <- optional: a second speaker (a mascot or character) and the voice it speaks with
    Spotter: Hi, I'm Spotter!              <- a sentence that speaker says (anywhere a Say: could go)

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
    images: list = dataclasses.field(default_factory=list)  # names of media-library images this slide should show ("Image:")
    speakers: list = dataclasses.field(default_factory=list)  # who says each sentence of `say` ("" = the narrator)
    acts: list = dataclasses.field(default_factory=list)      # what a character does between sentences: {"at": sentence index it comes before, "who": name, "do": text}
    shown: list = dataclasses.field(default_factory=list)     # indices of sentences a character says that are also printed on the slide (a speech bubble)

    def speaker(self, i): return self.speakers[i] if i < len(self.speakers) else ""

    def cast(self):
        """The characters that speak or act on this slide, in order of first appearance."""
        names = [w for w in self.speakers if w] + [a["who"] for a in self.acts]
        return list(dict.fromkeys(names))


@dataclasses.dataclass
class Module:
    title: str
    subtitle: str = ""
    intro: list = dataclasses.field(default_factory=list)     # narration for the title slide
    slides: list = dataclasses.field(default_factory=list)
    voices: dict = dataclasses.field(default_factory=dict)   # character name -> voice spec (None: the character's own voice from the media library)
    intro_speakers: list = dataclasses.field(default_factory=list)
    intro_acts: list = dataclasses.field(default_factory=list)
    intro_shown: list = dataclasses.field(default_factory=list)

    @property
    def sentences(self): return len(self.intro) + sum(len(s.say) for s in self.slides)

    @property
    def words(self): return sum(len(t.split()) for t in self.intro + [x for s in self.slides for x in s.say])

    def to_dict(self): return dataclasses.asdict(self)


MARKER = re.compile(r"^(title|subtitle|say|show|note|hold|image)\s*:\s*(.*)$", re.I)
MAX_HOLD = 30.0


def parse_hold(value, n):
    """'Hold: 3', '3s' or '2.5 seconds' -> seconds."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:s|sec|secs|second|seconds)?", value.strip(), re.I)
    if not m: raise ScriptError(f"Line {n}: 'Hold:' needs a number of seconds, like 'Hold: 3'.")
    seconds = float(m.group(1))
    if seconds > MAX_HOLD: raise ScriptError(f"Line {n}: 'Hold:' can be at most {MAX_HOLD:g} seconds.")
    return seconds
# A character is declared with "Voice: Spotter = Puppy" (a voice, optionally "Puppy, pitch +2, pace 1.1"), or simply by using it:
# a line "Spotter say: …" / "Spotter animate: …" introduces it (it then speaks with the voice set in the media library).
VOICE_LINE = re.compile(r"^voice\s*:\s*([^=:]{1,30}?)\s*=\s*(.+?)\s*$", re.I)
DEFAULT_CHARACTER_VOICE = "puppy"
NAME = r"[A-Z][A-Za-z0-9'’-]{1,19}"
NOT_NAMES = {"narrator", "narration", "scene", "note", "show", "say", "title", "subtitle", "hold", "image", "visual", "voice", "on", "the", "we", "you", "it", "he", "she", "they", "this", "that", "here"}
# "Spotter say hello" / "Spotter animate wink" work without a colon; the other forms (and the third-person "says") need one,
# so a narration sentence that happens to begin with the name is never taken for an instruction.
_PLAIN, _COLON = "say|speak|bubble|caption|animate|act", "says|speaks|bubbles|captions|animates|acts|print|prints|write|writes|type|types|perform|performs"
KIND_OF = {"say": "say", "says": "say", "speak": "say", "speaks": "say", "bubble": "bubble", "bubbles": "bubble", "caption": "bubble", "captions": "bubble",
           "print": "bubble", "prints": "bubble", "write": "bubble", "writes": "bubble", "type": "bubble", "types": "bubble",
           "animate": "act", "animates": "act", "act": "act", "acts": "act", "perform": "act", "performs": "act"}
AUTO_ACTOR = re.compile(rf"^({NAME})\s+(?:{_PLAIN}|{_COLON})\s*:|^({NAME})\s*:\s*(?:animate|animates|act|acts)\b", re.I)


def voice_id(value, n=0):
    """A voice spec from what a script says: 'Puppy', 'Puck', 'am_puck', or with changes, 'Puck, pitch +4, pace 1.1' (or 'Puck +4').
    The spec is 'base voice' alone, or 'base|semitones|pace'. A narrator voice or a character voice can be named."""
    from html2mp4 import cli
    text = (value or "").strip().strip('"“”')
    if not text: return cli.voice_spec(DEFAULT_CHARACTER_VOICE)
    pitch = pace = None
    m = re.search(r"(?:,|\s)\s*(?:pitch\s*)?([+-]\d+(?:\.\d+)?)(?:\s*(?:semitones?|st))?\s*(?=,|$)", text, re.I)
    if m: pitch = float(m.group(1)); text = (text[:m.start()] + text[m.end():]).strip(" ,")
    m = re.search(r"(?:,|\s)\s*(?:pace|speed|rate)\s*[:x ]?\s*(\d+(?:\.\d+)?)x?\s*(?=,|$)", text, re.I)
    if m: pace = float(m.group(1)); text = (text[:m.start()] + text[m.end():]).strip(" ,")
    spec = cli.voice_spec(text.strip(" ,"))
    if spec is None:
        names = [v[0] for v in cli.VOICES.values()] + [v[0] for v in cli.CHARACTER_VOICES.values()]
        raise ScriptError(f"Line {n}: there's no voice called “{value}”. Choose one of: {', '.join(names)}.")
    base, p0, k0 = cli.split_voice(spec)
    if pitch is not None: p0 = pitch
    if pace is not None:
        if not 0.5 <= pace <= 1.6: raise ScriptError(f"Line {n}: pace is a speed from 0.5 to 1.6, like 'pace 1.1'.")
        k0 = pace
    return cli.join_voice(base, p0, k0)


def _declared(text):
    """The characters a script names, as {name: voice spec or None}, from "Voice:" lines and from lines that address a character."""
    out, seen = {}, {}
    def add(name, spec=None):
        key = name.lower()
        if key in seen:
            if spec is not None: out[seen[key]] = spec
            return
        seen[key] = name; out[name] = spec
    for n, raw in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        line = raw.strip()
        m = VOICE_LINE.match(line)
        if m:
            name = " ".join(m.group(1).split())
            if name.lower() in ("narrator", "narration", "over"): raise ScriptError(f"Line {n}: the narrator's voice is chosen in Settings; 'Voice:' names a second speaker, like 'Voice: Spotter = Puppy'.")
            if not re.fullmatch(NAME.replace("{1,19}", "{0,28}"), name): raise ScriptError(f"Line {n}: a character's name is one word starting with a capital letter, like 'Spotter'.")
            add(name, voice_id(m.group(2), n)); continue
        m = AUTO_ACTOR.match(line)
        if m:
            name = m.group(1) or m.group(2)
            if name.lower() not in NOT_NAMES: add(name)
    return out


def voices_in(text): return _declared(text)


def actor_line(line, voices):
    """(name, 'say' | 'bubble' | 'act', text) for a line addressed to a declared character, or None.
    'Spotter say: Hi' / 'Spotter say Hi' / 'Spotter: Hi' speak; 'Spotter bubble: Hi' speaks and prints it; 'Spotter animate: wink' acts."""
    for name in voices:
        n = re.escape(name)
        m = re.match(rf"^{n}\s+(?:({_PLAIN})\b\s*:?|({_COLON})\s*:)\s*(.*)$", line, re.I)
        if m: return name, KIND_OF[(m.group(1) or m.group(2)).lower()], m.group(3).strip()
        m = re.match(rf"^{n}\s*:\s*(animate|animates|act|acts|perform|performs)\b\s*:?\s*(.*)$", line, re.I)
        if m: return name, "act", m.group(2).strip()
        m = re.match(rf"^{n}\s*:\s*(.*)$", line, re.I)
        if m: return name, "say", m.group(1).strip()
    return None


def _speaker_add(m, slide, who, kind, value, n, split=False):
    """Record a line a character says or does on `slide` (None: before the first slide). `value` may still hold the quotes."""
    text = _unquote(value)
    if not text: raise ScriptError(f"Line {n}: “{who} {'animate' if kind == 'act' else 'say'}:” has nothing after it" +
                                    (": say what the animation should be, like “wave” or “wag his tail”." if kind == "act" else "."))
    say, speakers, acts, shown = (slide.say, slide.speakers, slide.acts, slide.shown) if slide else (m.intro, m.intro_speakers, m.intro_acts, m.intro_shown)
    if kind == "act":
        if not re.search(r"[A-Za-z]", text): raise ScriptError(f"Line {n}: say what {who} should do, like “{who} animate: wave”.")
        acts.append({"at": len(say), "who": who, "do": " ".join(text.split())}); return 0
    pieces = split_sentences(text) if split else [text]
    speakers += [""] * (len(say) - len(speakers))
    for t in pieces:
        speakers.append(who); say.append(t)
        if kind == "bubble": shown.append(len(say) - 1)
    return len(pieces)
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
    m = Module(title="", subtitle="", voices=voices_in(text))
    slide, last = None, None            # last = (kind, target) for continuation lines
    for n, raw in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("//"):
            last = None if not line else last
            continue
        if VOICE_LINE.match(line): last = None; continue
        sp = actor_line(line, m.voices)
        if sp:
            who, kind, value = sp
            _speaker_add(m, slide, who, kind, value, n)
            last = ("say", slide) if kind != "act" else None; continue
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
            elif kind == "image":
                if not value: raise ScriptError(f"Line {n}: 'Image:' needs the name of an image from the media library.")
                slide.images += [p for p in SPLIT_SHOW.split(value) if p]; last = None
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

    _even(m)
    if title: m.title = title.strip()
    if subtitle: m.subtitle = subtitle.strip()
    if not m.title: raise ScriptError("The script needs a title: add 'Title: …' as the first line.")
    if not m.slides: raise ScriptError("The script has no slides: start each slide with '## Slide title'.")
    for s in m.slides:
        if not s.say: raise ScriptError(f"Slide “{s.title}” has no narration: add at least one 'Say:' line.")
    return m


def _even(m):
    """Every sentence has a speaker entry ("" = the narrator), and a module with nobody else speaking has none at all."""
    for s in m.slides:
        s.speakers = (s.speakers + [""] * len(s.say))[:len(s.say)] if any(s.speakers) else []
        for a in s.acts: a["at"] = min(a["at"], len(s.say))
    m.intro_speakers = (m.intro_speakers + [""] * len(m.intro))[:len(m.intro)] if any(m.intro_speakers) else []


def _parse_scenes(text, title, subtitle):
    m = Module(title="", subtitle="", voices=voices_in(text))
    slide, head, in_screen, quoted = None, [], False, None      # quoted: who is speaking inside a quote that opened on an earlier line
    for n, raw in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("//"):
            in_screen = False if not line else in_screen
            continue
        if VOICE_LINE.match(line): continue
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
        if mk and mk.group(1).lower() == "image":
            slide.images += [p for p in SPLIT_SHOW.split(mk.group(2)) if p]; in_screen = False; continue
        if in_screen and not slide.say and line.endswith((":",)) is False and len(line) < 200 and not re.search(r"[.!?]\s+[A-Z]", line):
            slide.screen = f"{slide.screen} {line}".strip(); continue      # a wrapped On screen: description
        in_screen = False
        who, kind = quoted or ("", "say")                               # inside a quote that opened on an earlier line, it is still that character
        nar = NARRATION.match(line)
        sp = None if quoted else actor_line(line, m.voices)
        if nar: line, who, kind = nar.group(1), "", "say"               # "Narration: …" labels what is said; it isn't said itself
        elif sp:
            who, kind, line = sp
            if kind == "act": _speaker_add(m, slide, who, "act", line, n); continue
        opens = line[:1] in QUOTES and sum(line.count(q) for q in QUOTES) == 1
        closes = line[-1:] in QUOTES and sum(line.count(q) for q in QUOTES) == 1
        quoted = (who, kind) if (opens and who) else (None if closes else quoted)
        if who:
            _speaker_add(m, slide, who, kind, line, n, split=True)
        else:
            line = _unquote(line)
            if line:
                said = split_sentences(line)
                slide.speakers += [""] * (len(slide.say) - len(slide.speakers)) + [""] * len(said)
                slide.say += said
    if head:
        first = head[0]
        m.title = re.sub(r"^(?:one\s+)?micro-?learning\s*[:\-–—]\s*", "", first, flags=re.I).strip()
        if len(head) > 1: m.subtitle = " ".join(head[1:])[:120]
    _even(m)
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
