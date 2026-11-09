"""Design a module's slides with Claude, then check and fix them until they're clean.

    design(module, brand)                         # first design of every slide
    design(module, brand, previous=..., only=[…], feedback="…")   # revise some slides

Claude returns, for each slide, the HTML for its body area and scoped CSS. The composer wraps them (stage, theme,
narration list, footer), the checker renders every narration step, and anything wrong goes back to Claude with the
failing step's screenshot, for up to two fix rounds. The narration itself never comes from Claude: it is copied
from the script.
"""
import base64, dataclasses, re

from html2mp4 import ai, compose, config, verify

MAX_FIX_ROUNDS = 2

SYSTEM = """You are a senior presentation designer making slides for narrated training videos. Each slide is 1280x720 and is
shown while a narrator reads the script; elements appear on screen as the narrator says the matching words.

# What you return
For each slide you are asked to design: `html` (the content of the slide's body area, which is 1120x560 px and starts
below a 64px top margin; the footer, logo and slide-progress dots are added for you) and `css` (rules for that html).
Use plain HTML and inline SVG only.

# Reveals (timing is driven by the narration)
- Each slide's narration is a numbered list of sentences (steps 0, 1, 2...). An element that appears during the
  narration carries `data-c="N"`: it becomes visible when sentence N starts, and stays.
- Add `data-cue="exact words"` (copied from sentence N) so the element appears when the narrator says those words. Use it
  whenever a sentence names several things in turn ("curious, ownership, perseverance"): each one gets its own cue.
- `data-d="0.3"` adds a small stagger (0 to 1 second) after the cue. Never use it to sync with speech; use data-cue.
- The slide heading carries data-c="0". Reveal what each sentence talks about when it talks about it. Sentences that
  need no visual reveal nothing. Elements without data-c are visible from the start; only use that for quiet backdrop shapes.
- Put data-c on the outermost element that should appear (a card), not on every child inside it.

# Layout rules (a checker renders every step and rejects violations; fix list: overflow, overlap, bounds, font, contrast)
- Use flexbox or grid, not absolute positions. Boxes must be sized so their text fits with at least 16px padding on
  every side; let text wrap (never white-space:nowrap); give long labels room for two lines. Keep at least 24px between
  boxes, and nothing may overlap (add data-overlay only for deliberate layering such as a glow).
- Everything must stay inside the 1120x560 body area, clear of the footer.
- A slide should hold one idea. Prefer 2 to 6 clear blocks. Leave generous whitespace; fill the area sensibly (don't
  leave a large empty band, and don't cram).
- Prefer cards, numbered steps, side-by-side comparisons, simple columns and big statements. Do NOT use connector
  lines, arrows between boxes, hubs-and-spokes or decorative rules: viewers dislike them. If a line is truly needed it
  must be straight, evenly spaced and aligned to the grid.
- Keep one visual language across all slides in the module: the same heading position and size, the same card style
  (radius, padding, border), the same spacing. Vary the layout only where the content differs.

# Type (only these sizes exist; the checker rejects any other)
Use the classes `t-display` (96px), `t-title` (64px), `t-heading` (44px), `t-lead` (28px), `t-body` (22px), `t-small`
(16px) or `font-size:var(--fs-heading)` etc. Slide headings use t-heading. Never go below 16px. Use `t-eyebrow` for
small uppercase labels. Fonts are set by the classes; never write font-family.

# Colour
Use only CSS variables: `--bg --text --accent --accent2 --surface --surface2 --line --muted --faint --accent-soft` and the
brand palette `--c-<name>` listed below. Never write hex colours. Follow the brand design rules exactly. Text must have
at least 4.5:1 contrast against its background (3:1 for 24px+). Gradient text must use background-clip:text.

# Ready-made classes
`stack` (column, 24px gap), `row` (children share the width, 24px gap), `grid` (add your own grid-template-columns),
`card` (surface, border, 20px radius, 28px padding), `pill`, plus the t-* type classes above.

# SVG
Use an explicit viewBox equal to the size you draw at (`width="1120" height="420" viewBox="0 0 1120 420"`) so 1 unit = 1px.
Style text with the t-* classes. Text must sit fully inside its shape. Give each svg an aria-label.

# Content
- Use the exact on-screen text you are given. Where only a description is given, write short labels using words from
  the narration. Never add facts, numbers, names, examples or claims that aren't in the script. Do not copy long
  narration sentences onto the slide. Never use a banned term.
- Do not draw the brand logo or footer; they are added automatically.

# Technical limits
No scripts, event handlers, external links or fonts, images, `url()`, `@import`, animations or `@keyframes`, and no
`position:fixed`. Every CSS selector must start with the slide's id (e.g. `#s2 .card{...}`).

Return one entry per requested slide, using the ids you were given, and a one-line `summary` of its layout."""

SLIDE_SCHEMA = {"type": "object", "properties": {
    "id": {"type": "string"}, "layout": {"type": "string"}, "summary": {"type": "string"},
    "html": {"type": "string"}, "css": {"type": "string"}},
    "required": ["id", "layout", "summary", "html", "css"], "additionalProperties": False}
SCHEMA = {"type": "object", "properties": {"slides": {"type": "array", "items": SLIDE_SCHEMA}},
          "required": ["slides"], "additionalProperties": False}

CRITIQUE_SCHEMA = {"type": "object", "properties": {"problems": {"type": "array", "items": {
    "type": "object", "properties": {"slide": {"type": "string"}, "severity": {"type": "string", "enum": ["must", "nice"]},
                                     "problem": {"type": "string"}, "fix": {"type": "string"}},
    "required": ["slide", "severity", "problem", "fix"], "additionalProperties": False}}},
    "required": ["problems"], "additionalProperties": False}

CRITIQUE_SYSTEM = """You are a meticulous design reviewer. You are shown screenshots of finished training slides (each at the
moment everything has appeared) and the brand rules they must follow. Report only problems a viewer would notice:
weak hierarchy, awkward or uneven spacing, large empty areas, crowded blocks, misaligned items, lines or decoration that
look bad, text that is hard to read, a layout that doesn't suit its content, a slide that looks different in style from the
others, or a brand-rule violation. Mark `must` only for clear defects; everything else is `nice`. For each problem give a
concrete `fix`. If the slides look good, return no problems.

Ignore the footer strip (logo, progress dots): it is added automatically and already follows the brand rules. Screenshots
are shrunk, so don't judge small sizes from them; the type sizes and contrast are checked separately by measurement."""


def slide_ids(module): return [f"s{i + 1}" for i in range(len(module.slides))]


def _digest(reference_html, limit=45000):
    """A style reference without its player script or embedded assets, trimmed to a size worth sending."""
    t = re.sub(r"<script\b.*?</script>", "", reference_html, flags=re.S | re.I)
    t = re.sub(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=]{100,}", "data:,", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t[:limit]


def _brand_text(brand, glossary):
    pal = "\n".join(f"- --c-{n}: {c['hex']} ({c['group']}) {c.get('usage', '')}".rstrip() for n, c in compose.palette_names(brand))
    rules = "\n".join(f"- {r}" for r in brand.get("rules", []))
    return (f"Slides use the {brand['style']} style: --bg {brand['background']}, --text {brand['text']}, --accent {brand['accent']}, "
            f"--accent2 {brand['accent2']}. Heading font {brand['heading_font']} (--hfont), body font {brand['body_font']} (--bfont).\n"
            + (f"\nBrand palette:\n{pal}\n" if pal else "") + (f"\nBrand design rules:\n{rules}\n" if rules else "")
            + (f"\nBanned terms (never use): {', '.join(glossary['banned'])}\n" if glossary.get("banned") else "")
            + (f"\nApproved terms (use exactly as written): {', '.join(glossary['approved'])}\n" if glossary.get("approved") else ""))


def _scenes_text(module, ids):
    out = []
    for sid, s in zip(slide_ids(module), module.slides):
        if sid not in ids: continue
        head = f"## Slide {sid}: {s.title}" + (f"   (the author's timing: {s.timing})" if s.timing else "")
        lines = [head]
        if s.show: lines.append("Exact on-screen text (use verbatim): " + " | ".join(f"“{x}”" for x in s.show))
        if s.screen: lines.append(f"The author's description of what should be on screen: {s.screen}")
        if s.note: lines.append(f"Design note: {s.note}")
        lines.append("Narration steps:")
        lines += [f"  {i}: {t}" for i, t in enumerate(s.say)]
        out.append("\n".join(lines))
    return "\n\n".join(out)


def _current_text(slides, ids):
    return "\n\n".join(f"### {sid} (layout: {slides[sid]['layout']})\nhtml:\n{slides[sid]['html']}\ncss:\n{slides[sid]['css']}" for sid in ids if sid in slides)


def _image(jpeg): return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(jpeg).decode()}}


def _clean(slide):
    return {"layout": re.sub(r"[^a-z0-9-]+", "-", slide["layout"].lower()).strip("-") or "custom", "summary": slide["summary"].strip(),
            "html": slide["html"].strip(), "css": slide["css"].strip()}


class Run:
    """Accumulates the cost and a plain-language log of what happened."""
    def __init__(self, progress): self.cost, self.calls, self.log, self._p = 0.0, 0, [], progress or (lambda f, label: None)

    def say(self, f, label): self._p(f, label); self.log.append(label)

    def call(self, system, content, schema, effort, label=None, lo=0.05, hi=0.45, total=0):
        """One Claude call; while its answer streams in, report how many slides are done (counted from the JSON)."""
        last = [-1]
        if label and total: self._p(lo, f"{label}: planning the layouts" if total > 1 else label)
        def on_text(text):
            done = min(text.count('"summary"'), total) if total else 0
            if label and total and done != last[0]:           # report only when another slide has been completed
                last[0] = done
                self._p(lo + (hi - lo) * done / total, f"{label} ({done} of {total} done)" if done < total else label)
        data, usage = ai.structured(system, content, schema, effort=effort, max_tokens=48000, on_text=on_text)
        self.cost += ai.cost(usage); self.calls += 1
        return data


def design(module, brand, *, glossary=None, reference=None, previous=None, only=None, feedback="", progress=None, polish=True,
           timing_note=""):
    """Design (or revise) slides. Returns {"html", "slides", "issues", "cost", "calls", "log"}."""
    glossary = glossary or config.glossary()
    ids = slide_ids(module)
    only = [i for i in (only or ids) if i in ids]
    slides = {k: dict(v) for k, v in (previous or {}).items() if k in ids}
    run = Run(progress)
    brand_text = _brand_text(brand, glossary)
    ref = _digest(reference) if reference else ""
    banned = glossary.get("banned", [])

    # 1. the design (or the revision)
    missing = [i for i in only if i not in slides]
    revising = bool(slides) and bool(feedback)
    intro = (f"Brand:\n{brand_text}\n"
             + (f"\nA module previously designed for this brand. Match its visual language (colour use, type, shapes, spacing), not its content:\n<reference>\n{ref}\n</reference>\n" if ref else "")
             + f"\nModule: “{module.title}”" + (f" ({module.subtitle})" if module.subtitle else "") + "\n")
    if not revising and not missing:
        pass                                              # nothing to design: just check and polish what's there
    elif revising:
        run.say(0.05, "Applying your feedback")
        content = (intro + "\nThe current design of the slides to change (and the others, for consistency):\n" + _current_text(slides, ids)
                   + f"\n\nThe slides' narration and on-screen text:\n{_scenes_text(module, ids)}\n"
                   + (f"\n{timing_note}\n" if timing_note else "")
                   + f"\nFeedback to apply: {feedback}\n\nReturn the updated design only for the slides that need to change, from: {', '.join(only)}. "
                     "Change only what the feedback asks for; keep everything else about those slides the same.")
    else:
        run.say(0.05, "Designing the slides")
        content = (intro + (f"\nThe slides already designed for this module (keep the same look and feel):\n{_current_text(slides, ids)}\n" if slides else "")
                   + (f"\nThe author also asks: {feedback}\n{timing_note}\n" if feedback else "")
                   + f"\nDesign these slides:\n\n{_scenes_text(module, missing)}\n\nReturn one entry for each of: {', '.join(missing)}.")
    if revising or missing:
        only_now = only if revising else missing
        _merge(slides, run.call(SYSTEM, content, SCHEMA, "high", "Designing the slides" if not revising else "Applying your feedback",
                                total=len(only_now)), only_now)

    # 2. check, and fix what the checker finds
    # Mechanical problems get MAX_FIX_ROUNDS fix rounds. The design review then runs once the checks are clean (when something
    # was designed or revised; polish="always" also reviews an unchanged design) and gets one fix round of its own.
    issues, page, reviewed = [], "", (not polish) or (polish is True and not (revising or missing))
    rounds_left, review_rounds_left, n = MAX_FIX_ROUNDS, 1, 0
    while True:
        run.say(0.45 + 0.04 * n, "Checking every slide, step by step"); n += 1
        page, issues, shots = _check(module, brand, slides, banned)
        errors = [i for i in issues if i.severity == "error"]
        if not errors and not reviewed:
            reviewed = True
            problems = _critique(run, module, brand_text, shots, slides)
            if set(only) != set(ids):                      # a targeted change doesn't touch (or re-judge) the other slides
                problems = [x for x in problems if x["slide"] in only]
            issues += [verify.Issue(p["slide"], 0, "design", "error", f"{p['problem']} Fix: {p['fix']}") for p in problems if p["severity"] == "must"]
            issues += [verify.Issue(p["slide"], 0, "design", "warn", f"{p['problem']} Suggestion: {p['fix']}") for p in problems if p["severity"] == "nice"]
            errors = [i for i in issues if i.severity == "error"]
        if not errors: break
        if any(i.kind != "design" for i in errors):
            if rounds_left == 0: break
            rounds_left -= 1
        else:
            if review_rounds_left == 0: break
            review_rounds_left -= 1
        bad = sorted({i.slide for i in errors if i.slide in slides})
        if not bad: break
        run.say(0.6 + 0.05 * n, f"Fixing {len(errors)} problem{'s' if len(errors) != 1 else ''} found")
        text = "These slides have problems the checker or the design review found. Fix every one without changing what the slide says " \
               "or reveals, then return the corrected slides.\n\nProblems:\n" + "\n".join(f"- {i.slide} (step {i.step}): {i.message}" if i.step else f"- {i.slide or 'module'}: {i.message}"
                                                                           for i in errors) \
               + f"\n\nCurrent design:\n{_current_text(slides, bad)}\n\nNarration and on-screen text:\n{_scenes_text(module, bad)}\n\nBrand:\n{brand_text}\n"
        blocks = [{"type": "text", "text": text}]
        for sid in bad:
            if (sid, "first") in shots:
                step, jpeg = shots[(sid, "first")]
                blocks += [{"type": "text", "text": f"Screenshot of {sid} at step {step}, where a problem first appears:"}, _image(jpeg)]
        _merge(slides, run.call(SYSTEM, blocks, SCHEMA, "medium", "Fixing the slides", lo=0.6 + 0.05 * n, hi=0.65 + 0.05 * n, total=len(bad)), bad)
    run.say(1.0, "Done")
    return {"html": page, "slides": slides, "issues": issues, "cost": run.cost, "calls": run.calls, "log": run.log}


def _merge(slides, data, wanted):
    got = {s["id"]: s for s in data["slides"]}
    for sid in wanted:
        if sid in got: slides[sid] = _clean(got[sid])


def _check(module, brand, slides, banned):
    """Assemble the module and inspect it. Returns (html, issues, screenshots)."""
    ids = slide_ids(module)
    issues = []
    for sid in ids:
        if sid not in slides: issues.append(verify.Issue(sid, 0, "missing", "error", f"{sid} has not been designed yet.")); continue
        for msg in verify.static_issues(sid, slides[sid]["html"], slides[sid]["css"], banned):
            issues.append(verify.Issue(sid, 0, "rule", "error", msg))
    if any(i.kind == "missing" for i in issues): return "", issues, {}
    page = compose.assemble(module, brand, [(slides[s]["layout"], slides[s]["html"]) for s in ids], "\n".join(slides[s]["css"] for s in ids))
    for sid, msg in compose.check_detailed(page, module): issues.append(verify.Issue(sid, 0, "narration", "error", msg))
    r = verify.inspect(page, module, banned)
    return page, issues + r["issues"], r["shots"]


def _critique(run, module, brand_text, shots, slides):
    run.say(0.5, "Reviewing the design")
    blocks = [{"type": "text", "text": f"Brand:\n{brand_text}\nThe finished slides follow, one screenshot each."}]
    for sid in slide_ids(module):
        if (sid, "last") in shots: blocks += [{"type": "text", "text": f"Slide {sid}:"}, _image(shots[(sid, "last")][1])]
    try:
        return run.call(CRITIQUE_SYSTEM, blocks, CRITIQUE_SCHEMA, "medium")["problems"]
    except ai.AIError:
        return []          # a failed review shouldn't fail the design
