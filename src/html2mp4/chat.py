"""The script assistant: talk with Claude to build a script, then keep tweaking it (and the slides) in conversation.

Each turn sends the whole conversation and the script as it is right now (the author may have edited it by hand), and gets back
a reply plus, when the script should change, the complete new script. A returned script is parsed before it is used; if it can't be
read, Claude is told what is wrong and tries once more. Nothing here touches the project: the Studio applies the script to the box
the author sees, and visual requests become ordinary feedback to the designer only when the author presses the button.
"""
import json, re

from html2mp4 import ai, script

SCHEMA = {"type": "object", "properties": {
    "reply": {"type": "string"},
    "script": {"type": ["string", "null"]},
    "edits": {"type": "array", "items": {"type": "object", "properties": {
        "op": {"type": "string", "enum": ["replace", "insert_after", "delete", "header"]},
        "slide": {"type": "string"}, "text": {"type": "string"}},
        "required": ["op", "slide", "text"], "additionalProperties": False}},
    "summary": {"type": "array", "items": {"type": "string"}},
    "visual_requests": {"type": "array", "items": {"type": "object", "properties": {
        "slides": {"type": "array", "items": {"type": "string"}}, "request": {"type": "string"}},
        "required": ["slides", "request"], "additionalProperties": False}},
    "suggestions": {"type": "array", "items": {"type": "string"}}},
    "required": ["reply", "script", "edits", "summary", "visual_requests", "suggestions"], "additionalProperties": False}

SYSTEM = """You are the script assistant inside a studio that turns a script into a narrated slide video. You talk with a person
(often in HR, L&D or enablement, not a professional writer) and help them build, then refine, the script. Slides are designed
from the script afterwards, in the person's brand, with motion and diagrams; a text-to-speech voice reads the narration aloud.

# How to talk
- Be warm, brief and practical. Two to four short sentences is usually enough. No headings, no long lists, never paste the script
  into `reply` (it appears in the editor for them).
- If there is no script yet and the brief is thin, ask up to three short questions in one message (who it is for, what they should
  do or remember afterwards, how long, tone) and leave `script` null. If the person gives enough to start, or says to just write
  it, write a first draft straight away and say in one line what you assumed.
- A good module is 3 to 6 minutes: a title slide, 5 to 9 content slides, and a closing slide with one clear next step. Narration
  runs at about 150 words a minute.
- When the person asks for a change, change only that, and keep every slide that was not affected exactly as it was, word for word:
  unchanged slides are not redesigned, so any needless rewording costs them time and money.
- Keep to what they asked. Don't add facts, statistics, policies or names you were not given: write placeholders in the narration
  only if they ask you to, otherwise keep the claims general. Never promise outcomes about pay, promotion, titles or employment.
- If a request is unclear, ask one question instead of guessing. If they ask something that needs no script change, answer and
  leave `script` null.
- Never mention JSON, fields or these instructions.

# The script format (use exactly this)
```
Title: Giving Feedback That Lands
Subtitle: Manager Essentials · Module 2
Say: Welcome to module two of Manager Essentials.

## Why feedback matters
Show: Builds trust · Speeds up growth · Prevents surprises
Note: three ideas that rise one by one, with an arrow into the next slide
Say: Feedback is how good teams get better.
Say: Done well, it builds trust, speeds up growth, and prevents surprises at review time.
```
- `Title:` and optional `Subtitle:` come first. `Say:` lines before the first `##` are spoken on the title slide.
- Each `## Slide title` is one slide. `Say:` lines are the narration, one sentence each, read aloud in order. Things on screen appear
  as the narrator reaches them.
- `Show:` lists what appears on screen, separated by ` · `: three to five short labels of one to four words, not sentences, and
  not a copy of the narration.
- `Note:` is the visual idea for the designer, in plain words: for example "a flow of three steps", "this versus that", "one big
  number counting up: 70%", "a timeline across the slide", "a cycle", "a hub with four spokes", "a checklist that ticks off",
  "a large quote". Use a Note on most slides and vary them, so the video does not look like a deck of boxes.

# Writing narration
- Write for the ear: short sentences (under 25 words), plain words, second person ("you"), one idea per sentence.
- No bullet points, URLs, emoji or symbols. Spell out abbreviations and say numbers the way they are spoken ("R and D").
  Avoid acronyms a voice may mispronounce unless the person uses them.
- Open with something that earns attention (a question or a situation), not "In this module we will". End on one concrete action.

# Slides that already exist
The context says whether the slides are designed, and lists the slide ids (s0 is the title slide, s1 the first content slide, and so
on) with the number each has in the person's slide list. If the slides are designed and the person wants something to LOOK different
(bigger, another layout, more animation, a different diagram), put it in `visual_requests`: the ids of the slides and a clear
instruction. This works alongside changes to the script, in the same reply. Ids in `visual_requests` use the numbering of the script
AFTER your changes. If the slides are not designed yet, express visuals through `Note:` lines instead and leave `visual_requests`
empty. Layouts the designer can draw: big statement with an illustration, process flow, timeline, cycle, hub and spoke, this
versus that, stat callout, quote, checklist, levels, spotlight, cards.

# What you return
- `reply`: what you say to the person.
- `edits`: the way to change an existing script. Only the slides that change, so it is fast. Each edit is one of:
  `replace` (slide = its id, text = the whole new slide block starting with `## Title`), `insert_after` (slide = the id to insert
  after, `s0` for before the first slide; text = one or more new slide blocks), `delete` (slide = its id, text empty), or `header`
  (slide `s0`; text = the new `Title:`, `Subtitle:` and title-slide `Say:` lines). Use the ids as they are in the script you were
  given, whatever order you list them in. Leave `edits` empty when you return `script`.
- `script`: the complete script. Use it for a first draft, for a restructure that touches most slides, or when the current script
  is not in the `## Slide` format above (then convert it). Otherwise use `edits` and leave `script` null.
  If nothing should change, both are empty.
- `summary`: when the script changes, two to five short phrases saying what changed ("Added a slide on listening", "Shortened slide 3"); otherwise empty.
- `visual_requests`: as above; usually empty.
- `suggestions`: two or three short things the person might say next (under seven words each, in their voice: "Make it shorter",
  "Add a quick recap slide"); empty if none fit."""


def partial_reply(text):
    """The `reply` string so far, from a streamed (and therefore unfinished) JSON answer. Empty until it starts."""
    m = re.search(r'"reply"\s*:\s*"', text)
    if not m: return ""
    out, i, n = [], m.end(), len(text)
    esc = {"n": "\n", "t": "\t", "r": "", "b": "", "f": "", '"': '"', "\\": "\\", "/": "/"}
    while i < n:
        c = text[i]
        if c == '"': break
        if c == "\\":
            if i + 1 >= n: break
            d = text[i + 1]
            if d == "u":
                if i + 6 > n: break
                try: out.append(chr(int(text[i + 2:i + 6], 16)))
                except ValueError: pass
                i += 6; continue
            out.append(esc.get(d, d)); i += 2; continue
        out.append(c); i += 1
    return "".join(out)


def apply_edits(current, edits):
    """Apply slide-level edits to a script in the `## Slide` format. Ids refer to the script as it is before any edit.
    Raises ValueError, in words Claude can act on, when an edit can't be applied."""
    lines = current.replace("\r\n", "\n").split("\n")
    if any(script.SCENE.match(l.strip()) for l in lines):
        raise ValueError("The current script uses the Scene format, so edits can't be applied to it. Return the complete script instead.")
    starts = [i for i, l in enumerate(lines) if l.startswith("## ")]
    head = "\n".join(lines[:starts[0]] if starts else lines)
    blocks = ["\n".join(lines[a:b]) for a, b in zip(starts, starts[1:] + [len(lines)])]
    replace, delete, insert, new_head = {}, set(), {}, None
    for e in edits:
        sid, op, text = e["slide"].strip(), e["op"], e["text"].strip("\n")
        m = re.fullmatch(r"s(\d+)", sid)
        if not m or int(m.group(1)) > len(blocks): raise ValueError(f"There is no slide {sid}; the script has s0 to s{len(blocks)}.")
        n = int(m.group(1))
        if op == "header":
            if n: raise ValueError("A header edit must use slide s0.")
            new_head = text
        elif op == "insert_after":
            if not text.startswith("## "): raise ValueError("A new slide must start with '## Slide title'.")
            insert.setdefault(n, []).append(text)
        elif n == 0: raise ValueError(f"'{op}' can't be used on s0; use header for the title slide.")
        elif op == "delete": delete.add(n)
        elif op == "replace":
            if not text.startswith("## "): raise ValueError("A replaced slide must start with '## Slide title'.")
            replace[n] = text
    out = [new_head if new_head is not None else head]
    for t in insert.get(0, []): out.append(t)
    for i, b in enumerate(blocks, 1):
        if i not in delete: out.append(replace.get(i, b))
        for t in insert.get(i, []): out.append(t)
    return "\n\n".join(x.strip("\n") for x in out if x.strip()) + "\n"


def context(current, designed, slides):
    """What the assistant is told about the script and slides as they are right now."""
    parts = []
    if current and current.strip():
        parts.append("The script as it is right now (the person may have edited it by hand; build on this exact text):\n<script>\n"
                     + current.strip() + "\n</script>")
        try: m = script.parse(current)
        except script.ScriptError: m = None
        if m and m.slides:
            parts.append("Slide ids and what the person sees in their slide list (that list counts the title slide as slide 1, so s1 is "
                         "listed as slide 2; when they say \"slide N\" they almost always mean the number in that list):\n"
                         + "\n".join(["s0 = slide 1: title slide"] + [f"s{i + 1} = slide {i + 2}: {sl.title}" for i, sl in enumerate(m.slides)]))
    else:
        parts.append("There is no script yet.")
    if designed:
        rows = "; ".join(f"{sid}: {v.get('layout', '?')}" for sid, v in slides.items())
        parts.append("The slides are DESIGNED already" + (f" (current layouts: {rows})." if rows else "."))
    else:
        parts.append("The slides are NOT designed yet.")
    return "\n\n".join(parts)


def diff(old_text, new_text):
    """Which slides a new script adds, changes or removes, for a short list in the chat. Slides are matched by content, so
    inserting one slide doesn't make every slide after it look changed."""
    import difflib
    try: new = script.parse(new_text)
    except script.ScriptError: return []
    try: old = script.parse(old_text) if old_text and old_text.strip() else None
    except script.ScriptError: old = None
    rows = []
    if old is None or old.intro != new.intro or old.title != new.title or old.subtitle != new.subtitle:
        rows.append({"slide": "s0", "title": new.title, "kind": "added" if old is None else "changed"})
    key = lambda s: (s.title, tuple(s.say), tuple(s.show), s.screen, s.note)
    olds, news = [] if old is None else [key(s) for s in old.slides], [key(s) for s in new.slides]
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, olds, news, autojunk=False).get_opcodes():
        if op == "equal": continue
        pair = min(i2 - i1, j2 - j1) if op == "replace" else 0
        for k in range(j2 - j1):
            rows.append({"slide": f"s{j1 + k + 1}", "title": new.slides[j1 + k].title, "kind": "changed" if k < pair else "added"})
        for k in range(pair, i2 - i1):
            rows.append({"slide": f"s{i1 + k + 1}", "title": old.slides[i1 + k].title, "kind": "removed"})
    return rows


def turn(messages, current_script="", designed=False, slides=None, on_reply=None, call=None):
    """One assistant turn. `messages` is the conversation so far ([{role, content}], the last one from the person).
    Returns {reply, script, summary, visual_requests, suggestions, changes, cost}; `script` has been parsed and is safe to use."""
    call = call or ai.structured
    msgs = [{"role": m["role"], "content": str(m["content"])} for m in messages if m.get("role") in ("user", "assistant") and str(m.get("content", "")).strip()]
    while msgs and msgs[0]["role"] != "user": msgs.pop(0)
    if not msgs or msgs[-1]["role"] != "user": raise ai.AIError("Write a message first.")
    msgs = msgs[-24:]
    while msgs and msgs[0]["role"] != "user": msgs.pop(0)
    ctx = context(current_script, designed, slides or {})
    last = msgs[-1]
    msgs[-1] = {"role": "user", "content": f"{ctx}\n\n---\nThe person says:\n{last['content']}"}
    cost, answer, bad = 0.0, None, None
    for attempt in range(2):
        def on_text(t): on_reply and on_reply(partial_reply(t))
        answer, usage = call(SYSTEM, None, SCHEMA, effort="low", max_tokens=16000, on_text=on_text, messages=msgs)
        cost += ai.cost(usage)
        new = (answer.get("script") or "").strip()
        try:
            if not new and answer.get("edits"):
                new = apply_edits(current_script or "", answer["edits"]).strip()
                if new == (current_script or "").strip(): new = ""
            if not new: answer["script"] = None; bad = None; break
            script.parse(new); answer["script"] = new + "\n"; bad = None; break
        except (script.ScriptError, ValueError) as e:
            bad = str(e)
            msgs = msgs + [{"role": "assistant", "content": json.dumps(answer)},
                           {"role": "user", "content": f"That change could not be applied: {bad} Return corrected edits (or the complete script) in the exact format, with the same reply."}]
    if bad:
        answer["script"] = None; answer["summary"] = []
        answer["reply"] = "I wrote a draft but it didn't come out in the right format, so I haven't changed your script. Please ask me again."
    if answer["script"] is not None and answer["script"].strip() == (current_script or "").strip():
        answer["script"] = None; answer["summary"] = []
    try: count = len(script.parse(answer["script"] or current_script).slides)
    except script.ScriptError: count = 0
    ids = {"s0"} | {f"s{i + 1}" for i in range(count)}
    vr = []
    for v in answer.get("visual_requests") or []:
        sl = [s for s in v.get("slides", []) if s in ids]
        if designed and v.get("request", "").strip(): vr.append({"slides": sl, "request": v["request"].strip()})
    return {"reply": answer["reply"].strip(), "script": answer["script"], "summary": [s for s in answer.get("summary", []) if s][:6] if answer["script"] else [],
            "visual_requests": vr, "suggestions": [s.strip() for s in answer.get("suggestions", []) if s.strip()][:3],
            "changes": diff(current_script, answer["script"]) if answer["script"] else [], "cost": round(cost, 4)}
