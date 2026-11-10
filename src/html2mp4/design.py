"""Design a module's slides with Claude, then check and fix them until they're clean.

    design(module, brand)                         # first design of every slide
    design(module, brand, previous=..., only=[…], feedback="…")   # revise some slides

Claude returns, for each slide, the HTML for its body area and scoped CSS. The composer wraps them (stage, theme,
narration list, footer), the checker renders every narration step, and anything wrong goes back to Claude with the
failing step's screenshot, for up to two fix rounds. The narration itself never comes from Claude: it is copied
from the script.
"""
import base64, concurrent.futures, dataclasses, re, threading, time

from html2mp4 import ai, compose, config, verify

MAX_FIX_ROUNDS = 2
MAX_PARALLEL = 4                 # simultaneous Claude calls when slides are designed or fixed side by side
# How hard Claude thinks for each kind of call. Fixes are mechanical (the checker says exactly what's wrong and the result is
# checked again), so they use less effort than a first design.
EFFORT = {"design": "high", "fix": "low", "review_fix": "medium", "critique": "medium"}

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
- Text conventions are shared by every slide: apply the brand's capitalisation rules (for example Title Case headings,
  uppercase eyebrow labels) to every heading and label, the same way on all slides; don't wrap card labels in quotation marks
  or end them with full stops unless they are quoted speech. When other slides are shown to you, copy their conventions exactly.

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

EXAMPLE_NARRATION = ["Feedback is how good teams get better.",
                     "Done well, it builds trust, speeds up growth, and prevents surprises at review time."]
EXAMPLE_HTML = """<h2 class="t-heading" data-c="0">Why feedback matters</h2>
<div class="grid fb-cards">
  <div class="card fb-card" data-c="1" data-cue="builds trust"><svg width="44" height="44" viewBox="0 0 44 44" aria-label="Trust"><circle cx="22" cy="22" r="20" fill="none" stroke="var(--accent)" stroke-width="2"/><path d="M13 23l6 6 12-13" fill="none" stroke="var(--accent)" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg><div><div class="t-small t-muted">01</div><div class="t-lead">Builds trust</div></div></div>
  <div class="card fb-card" data-c="1" data-cue="speeds up growth"><svg width="44" height="44" viewBox="0 0 44 44" aria-label="Growth"><circle cx="22" cy="22" r="20" fill="none" stroke="var(--accent)" stroke-width="2"/><path d="M13 29l7-8 5 4 6-9" fill="none" stroke="var(--accent)" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg><div><div class="t-small t-muted">02</div><div class="t-lead">Speeds up growth</div></div></div>
  <div class="card fb-card" data-c="1" data-cue="prevents surprises"><svg width="44" height="44" viewBox="0 0 44 44" aria-label="No surprises"><circle cx="22" cy="22" r="20" fill="none" stroke="var(--accent)" stroke-width="2"/><path d="M22 12v12M22 30v2" fill="none" stroke="var(--accent)" stroke-width="2.6" stroke-linecap="round"/></svg><div><div class="t-small t-muted">03</div><div class="t-lead">Prevents surprises</div></div></div>
</div>"""
EXAMPLE_CSS = """#s1 .fb-cards{grid-template-columns:repeat(3,1fr);margin-top:40px}
#s1 .fb-card{display:flex;flex-direction:column;justify-content:space-between;gap:48px;min-height:240px;padding:32px}"""

SYSTEM += """

# A complete example (a slide like this passes every check)
Script for slide s1, with the on-screen text "Builds trust · Speeds up growth · Prevents surprises". Narration steps:
""" + "\n".join(f"  {i}: {t}" for i, t in enumerate(EXAMPLE_NARRATION)) + """
A good answer for it (html and css; the heading carries data-c="0", and each card appears on the words that name it):
<html>
""" + EXAMPLE_HTML + """
</html>
<css>
""" + EXAMPLE_CSS + """
</css>
Note how: boxes have generous padding and room for their text; type comes only from t-* classes; colours only from variables;
cards share the width with a grid; there are no connector lines; and everything fits well inside the 1120x560 area."""

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
    """One design run: totals the cost, keeps a plain-language log, and reports progress, activity and Claude's live thinking.

    Calls may run side by side, so everything here is thread-safe and progress only ever moves forward."""
    def __init__(self, progress=None, activity=None, thought=None):
        self.cost, self.calls, self.log = 0.0, 0, []
        self._p, self._a, self._t = progress or (lambda f, label: None), activity or (lambda kind, text: None), thought or (lambda key, label, text: None)
        self._lock, self._last, self._thought_at = threading.Lock(), 0.0, {}
        self.written, self.total = set(), 0         # slides Claude has finished writing, out of the slides being designed

    def say(self, f, label):
        with self._lock:
            self._last = max(self._last, f); f = self._last
        self._p(f, label); self.log.append(label)

    def event(self, kind, text):
        self._a(kind, text); self.log.append(text)

    def add_usage(self, usage):
        with self._lock: self.cost += ai.cost(usage); self.calls += 1

    def call(self, system, content, schema, effort, *, name, watch_slides=False, ids=()):
        """One Claude call. While it runs: Claude's thinking summary goes to `thought`, and (for designs) each slide's plan
        appears as an event the moment Claude starts writing it."""
        started, previous = set(), [None]

        def on_text(text):
            if not watch_slides: return
            for sid, summary in re.findall(r'"id"\s*:\s*"(s\d+)"\s*,\s*"layout"\s*:\s*"[^"]*"\s*,\s*"summary"\s*:\s*"((?:[^"\\]|\\.)*)"', text):
                if sid in started: continue
                started.add(sid)
                if previous[0]:                                   # Claude has moved on, so the slide before this one is complete
                    with self._lock: self.written.add(previous[0])
                previous[0] = sid
                self.event("write", f"{name}: writing {slide_label(sid)}. {summary.replace(chr(92) + chr(34), chr(34))}")
                self._designing_progress()

        def on_thinking(text):
            now = time.time()
            if now - self._thought_at.get(name, 0) < 0.4: return
            self._thought_at[name] = now
            self._t(name, name, text[-420:])

        data, usage = ai.structured(system, content, schema, effort=effort, max_tokens=48000, on_text=on_text, on_thinking=on_thinking)
        self.add_usage(usage)
        if watch_slides:
            with self._lock: self.written.update(ids)
            self._designing_progress()
        self._t(name, name, "")                                        # this call is finished: clear its thought
        return data

    def _designing_progress(self):
        if self.total:
            done = min(len(self.written), self.total)
            self.say(0.08 + 0.32 * done / self.total, f"Designing the slides ({done} of {self.total} written)")


def expand_module_wide(problems, ids):
    """A review problem about "all" slides (or no particular slide) becomes one problem per slide when it must be fixed, so the
    fix has somewhere to go; as a suggestion it stays a note about the module."""
    out = []
    for p in problems:
        if p["slide"] in ids: out.append(p)
        elif p["severity"] == "must": out += [{**p, "slide": sid} for sid in ids]
        else: out.append({**p, "slide": ""})
    return out


def slide_label(sid): return "the title slide" if sid == "s0" else f"slide {sid[1:]}"


def plan_batches(ids, lead=2, parallel=MAX_PARALLEL):
    """Which slides each design call handles. The first `lead` slides are designed first, so they set the look that the others are
    then designed to match, side by side. Short modules (or `lead=0`) go in one call or fully in parallel."""
    ids = list(ids)
    if lead and len(ids) <= 3: return [ids]
    head, rest = ids[:lead], ids[lead:]
    size = max(1, -(-len(rest) // parallel)) if rest else 1
    return ([head] if head else []) + [rest[k:k + size] for k in range(0, len(rest), size)]


def _span(ids):
    """"slide 3", "slides 1–2", "slides 3, 5–6": a readable list of slides (the title slide is named on its own)."""
    nums = sorted(int(i[1:]) for i in ids if i != "s0")
    runs, k = [], 0
    while k < len(nums):
        j = k
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1: j += 1
        runs.append(str(nums[k]) if j == k else f"{nums[k]}–{nums[j]}")
        k = j + 1
    text = ", ".join(runs)
    parts = ["the title slide"] if "s0" in ids else []
    if nums: parts.append(("slides " if len(nums) > 1 else "slide ") + text)
    return " and ".join(parts)


def design(module, brand, *, glossary=None, reference=None, previous=None, only=None, feedback="", progress=None, polish=True,
           timing_note="", activity=None, thought=None, effort=None):
    """Design (or revise) slides. Returns {"html", "slides", "issues", "cost", "calls", "log"}."""
    glossary = glossary or config.glossary()
    efforts = {**EFFORT, **(effort or {})}
    ids = slide_ids(module)
    only = [i for i in (only or ids) if i in ids]
    slides = {k: dict(v) for k, v in (previous or {}).items() if k in ids}
    run = Run(progress, activity, thought)
    brand_text = _brand_text(brand, glossary)
    ref = _digest(reference) if reference else ""
    banned = glossary.get("banned", [])
    # The brand, its rules and the reference module are the same on every call, so they sit in the cached system prompt
    # (cheaper and faster for every call after the first).
    system = [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral", "ttl": "1h"}},
              {"type": "text", "text": f"Brand:\n{brand_text}\n"
               + (f"\nA module previously designed for this brand. Match its visual language (colour use, type, shapes, spacing), not its content:\n<reference>\n{ref}\n</reference>\n" if ref else ""),
               "cache_control": {"type": "ephemeral", "ttl": "1h"}}]
    head = f"Module: “{module.title}”" + (f" ({module.subtitle})" if module.subtitle else "") + "\n"

    # 1. the design (or the revision)
    missing = [i for i in only if i not in slides]
    revising = bool(slides) and bool(feedback)
    run.event("plan", f"Reading your script and brand: {len(module.slides)} slides, {module.sentences} sentences.")
    if revising:
        run.say(0.05, "Applying your feedback")
        run.event("plan", f"Applying your feedback to {_span(only) if set(only) != set(ids) else 'the whole module'}: “{feedback[:90]}”")
        run.total = len(only)
        batches = [only] if len(only) <= 3 else plan_batches(only, lead=0)

        def revise(batch, name):
            content = (head + "\nThe current design of the slides to change (and the others, for consistency):\n" + _current_text(slides, ids)
                       + f"\n\nThe slides' narration and on-screen text:\n{_scenes_text(module, ids)}\n"
                       + (f"\n{timing_note}\n" if timing_note else "")
                       + f"\nFeedback to apply: {feedback}\n\nReturn the updated design only for the slides that need to change, from: {', '.join(batch)}. "
                         "Change only what the feedback asks for; keep everything else about those slides the same.")
            return batch, run.call(system, content, SCHEMA, efforts["design"], name=name, watch_slides=True, ids=batch)
        _run_batches(run, batches, revise, slides, lambda b: _span(b), parallel_ok=True)
    elif missing:
        run.say(0.05, "Designing the slides: planning the layouts")
        run.total = len(missing)
        batches = plan_batches(missing, lead=0 if slides else 2)
        extra = f"\nThe author also asks: {feedback}\n{timing_note}\n" if feedback else ""

        def create(batch, name):
            established = [k for k in ids if k in slides]
            content = (head
                       + (f"\nThe slides already designed for this module. Match their look and feel exactly (card style, heading, spacing, type treatments, and text conventions such as capitalisation and punctuation):\n{_current_text(slides, established)}\n" if established else "")
                       + extra + f"\nDesign these slides:\n\n{_scenes_text(module, batch)}\n\nReturn one entry for each of: {', '.join(batch)}.")
            return batch, run.call(system, content, SCHEMA, efforts["design"], name=name, watch_slides=True, ids=batch)
        if len(batches) > 1:
            run.event("plan", f"Designing {_span(batches[0])} first, to set the look; then {_span(sum(batches[1:], []))} side by side to match it.")
        # the first batch alone (it sets the look), then the rest side by side; they are designed to match the first batch's finished slides
        _run_batches(run, batches[:1], create, slides, _span, parallel_ok=False)
        _run_batches(run, batches[1:], create, slides, _span, parallel_ok=True)

    # 2. check, and fix what the checker finds
    # Mechanical problems get MAX_FIX_ROUNDS fix rounds. The design review then runs once the checks are clean (when something
    # was designed or revised; polish="always" also reviews an unchanged design) and gets one fix round of its own.
    issues, page, reviewed = [], "", (not polish) or (polish is True and not (revising or missing))
    rounds_left, review_rounds_left, n = MAX_FIX_ROUNDS, 1, 0
    while True:
        run.say(0.45 + 0.02 * n, "Checking every slide, step by step"); n += 1
        run.event("check", "Rendering every step of every slide to check fit, overlap, type sizes and contrast.")
        page, issues, shots = _check(module, brand, slides, banned)
        errors = [i for i in issues if i.severity == "error"]
        if not errors: run.event("check", "The checker found nothing to fix.")
        else:
            run.event("check", f"The checker found {len(errors)} problem{'s' if len(errors) != 1 else ''}:")
            for i in errors[:6]: run.event("check", f"  {slide_label(i.slide) if i.slide else 'module'}" + (f", step {i.step}" if i.step else "") + f": {i.message[:140]}")
            if len(errors) > 6: run.event("check", f"  …and {len(errors) - 6} more.")
        if not errors and not reviewed:
            reviewed = True
            problems = expand_module_wide(_critique(run, module, brand_text, shots, slides), ids)
            if set(only) != set(ids):                      # a targeted change doesn't touch (or re-judge) the other slides
                problems = [x for x in problems if x["slide"] in only or not x["slide"]]
            issues += [verify.Issue(p["slide"], 0, "design", "error", f"{p['problem']} Fix: {p['fix']}") for p in problems if p["severity"] == "must"]
            issues += [verify.Issue(p["slide"], 0, "design", "warn", f"{p['problem']} Suggestion: {p['fix']}") for p in problems if p["severity"] == "nice"]
            errors = [i for i in issues if i.severity == "error"]
            run.event("review", "The design review found nothing to fix." if not problems else
                      f"The design review noted {sum(p['severity'] == 'must' for p in problems)} to fix and {sum(p['severity'] == 'nice' for p in problems)} suggestions.")
        if not errors: break
        review_only = all(i.kind == "design" for i in errors)
        if review_only:
            if review_rounds_left == 0: break
            review_rounds_left -= 1
        else:
            if rounds_left == 0: break
            rounds_left -= 1
        bad = sorted({i.slide for i in errors if i.slide in slides})
        if not bad: break
        run.say(0.6 + 0.04 * n, f"Fixing {_span(bad)}")
        run.event("fix", f"Fixing {_span(bad)}" + (" side by side." if len(bad) > 1 else "."))
        run.total = len(bad); run.written = set()
        _fix_slides(run, system, module, slides, errors, shots, bad, efforts["review_fix" if review_only else "fix"], brand_text)
    run.say(1.0, "Done")
    run.event("done", f"Done. About ${run.cost:.2f} of Claude usage.")
    return {"html": page, "slides": slides, "issues": issues, "cost": run.cost, "calls": run.calls, "log": run.log}


def _run_batches(run, batches, make, slides, name_of, parallel_ok):
    """Run `make(batch, name)` for each batch (side by side when allowed) and merge the results into `slides`."""
    if not batches: return
    if len(batches) == 1 or not parallel_ok:
        results = [make(b, name_of(b)) for b in batches]
    else:
        with concurrent.futures.ThreadPoolExecutor(min(MAX_PARALLEL, len(batches))) as ex:
            futures = [ex.submit(make, b, name_of(b)) for b in batches]
            results = [f.result() for f in futures]
    for batch, data in results: _merge(slides, data, batch)


def _fix_slides(run, system, module, slides, errors, shots, bad, effort, brand_text):
    """Each slide with problems is fixed in its own call, side by side: a fix only touches its own slide."""
    def one(sid):
        mine = [i for i in errors if i.slide == sid]
        shared = [i for i in errors if not i.slide]
        text = ("This slide has problems the checker or the design review found. Fix every one without changing what the slide says "
                "or reveals, then return the corrected slide.\n\nProblems:\n"
                + "\n".join(f"- (step {i.step}) {i.message}" if i.step else f"- {i.message}" for i in mine + shared)
                + f"\n\nCurrent design:\n{_current_text(slides, [sid])}\n\nNarration and on-screen text:\n{_scenes_text(module, [sid])}\n")
        blocks = [{"type": "text", "text": text}]
        if (sid, "first") in shots:
            step, jpeg = shots[(sid, "first")]
            blocks += [{"type": "text", "text": f"Screenshot of {sid} at step {step}, where a problem first appears:"}, _image(jpeg)]
        data = run.call(system, blocks, SCHEMA, effort, name=f"Fixing {slide_label(sid)}", watch_slides=False)
        with run._lock: run.written.add(sid)
        run.say(0.6 + 0.2 * len(run.written) / max(1, len(bad)), f"Fixing the slides ({len(run.written)} of {len(bad)} fixed)")
        return sid, data
    with concurrent.futures.ThreadPoolExecutor(min(MAX_PARALLEL, len(bad))) as ex:
        results = [f.result() for f in [ex.submit(one, sid) for sid in bad]]
    for sid, data in results: _merge(slides, data, [sid])


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
    run.event("review", "A design reviewer is looking at screenshots of the finished slides.")
    blocks = [{"type": "text", "text": f"Brand:\n{brand_text}\nThe finished slides follow, one screenshot each."}]
    for sid in slide_ids(module):
        if (sid, "last") in shots: blocks += [{"type": "text", "text": f"Slide {sid}:"}, _image(shots[(sid, "last")][1])]
    try:
        return run.call(CRITIQUE_SYSTEM, blocks, CRITIQUE_SCHEMA, EFFORT["critique"], name="Design review")["problems"]
    except ai.AIError:
        return []          # a failed review shouldn't fail the design
