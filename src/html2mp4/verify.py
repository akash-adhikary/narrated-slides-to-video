"""Check a composed module the way a person would, before anyone sees it.

Every narration step of every slide is rendered in headless Chromium in its fully-revealed state and measured:
text that doesn't fit its box, overlapping elements, content outside the slide, font sizes outside the type scale,
low contrast, words that aren't in the script, banned terms and script errors. Problems come back as plain-language
issues (and, for slides with errors, a screenshot of the first failing step) so they can be fixed automatically.
"""
import dataclasses, html, pathlib, re, tempfile

from html2mp4 import cli, compose

SAFE = (24, 24, 1256, 652)            # text must stay inside these stage bounds (left, top, right, bottom): clear of the footer
SCALE_TOLERANCE = 0.6
STOPWORDS = set("""a an the and or but if so of to in on at by for with from into over under as is are was were be been being it its this that
these those they them their there here we our us you your he she his her i me my not no do does did can could would should will
may might more most less very just also than then when what which who how why all any each some such only own same too up down out off
about again once""".split())

MEASURE_JS = r"""
(args) => {
  const [sid, allowed] = args;
  const slide = document.getElementById(sid);
  const out = {issues: [], texts: [], sizes: {}};
  const eff = e => { let o = 1; for (let n = e; n && n.nodeType === 1; n = n.parentElement) { const cs = getComputedStyle(n);
      if (cs.display === 'none' || cs.visibility === 'hidden') return 0; o *= parseFloat(cs.opacity); } return o; };
  const ctx = document.createElement('canvas').getContext('2d');
  const rgba = css => { ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = '#000'; ctx.fillStyle = css; ctx.fillRect(0, 0, 1, 1);
      const d = ctx.getImageData(0, 0, 1, 1).data; return [d[0], d[1], d[2], d[3] / 255]; };
  const lum = c => { const f = v => { v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); };
      return .2126 * f(c[0]) + .7152 * f(c[1]) + .0722 * f(c[2]); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
  const over = (a, b) => ({w: Math.min(a.right, b.right) - Math.max(a.left, b.left), h: Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top)});
  const label = t => t.trim().replace(/\s+/g, ' ').slice(0, 40);
  const hasBox = e => { const cs = getComputedStyle(e);
      return parseFloat(cs.borderTopWidth) > 0 && cs.borderTopStyle !== 'none' || rgba(cs.backgroundColor)[3] > .05 || cs.backgroundImage !== 'none'; };
  const foot = slide.querySelector('.slide-foot');

  // visible text, one entry per text node
  const nodes = [], walker = document.createTreeWalker(slide, NodeFilter.SHOW_TEXT);
  for (let n; (n = walker.nextNode());) {
    const t = n.textContent; if (!t.trim()) continue;
    const el = n.parentElement; if (!el || (foot && foot.contains(el)) || el.closest('script,style')) continue;
    if (eff(el) < .05) continue;
    const range = document.createRange(); range.selectNodeContents(n);
    const r = range.getBoundingClientRect(); if (r.width < 1 || r.height < 1) continue;
    nodes.push({n, el, t, r});
  }
  for (const {el, t, r} of nodes) {
    out.texts.push(t.trim());
    const cs = getComputedStyle(el), svgText = el instanceof SVGElement;
    let size = parseFloat(cs.fontSize);
    if (svgText) { const m = el.getScreenCTM && el.getScreenCTM(); if (m) size *= Math.hypot(m.a, m.b); }
    size = Math.round(size * 10) / 10; out.sizes[size] = (out.sizes[size] || 0) + 1;
    if (!allowed.some(a => Math.abs(a - size) <= %(tol)s))
      out.issues.push({kind: 'font', message: `“${label(t)}” is ${size}px; only these sizes are allowed: ${allowed.join(', ')}px (use the --fs-* variables or .t-* classes).`});
    // inside the slide, clear of the footer
    if (r.left < %(l)s || r.right > %(r)s || r.top < %(t)s || r.bottom > %(b)s)
      out.issues.push({kind: 'bounds', message: `“${label(t)}” runs outside the safe area of the slide (it must stay above the footer and inside the margins).`});
    // contrast against the nearest solid background
    const fill = svgText ? cs.fill : cs.color;
    const clipped = cs.webkitTextFillColor === 'rgba(0, 0, 0, 0)' || cs.backgroundClip === 'text' || cs.webkitBackgroundClip === 'text';
    if (!clipped && fill !== 'none') {
      let fg = rgba(fill), bg = null, gradient = false;
      for (let n = el; n && n.nodeType === 1; n = n.parentElement) { const s = getComputedStyle(n);
        if (s.backgroundImage !== 'none' && n !== el) { gradient = true; break; }
        const c = rgba(s.backgroundColor); if (c[3] > .5) { bg = c; break; } }
      if (!gradient) { bg = bg || rgba(getComputedStyle(document.getElementById('stage')).backgroundColor);
        fg = [0, 1, 2].map(i => fg[i] * fg[3] + bg[i] * (1 - fg[3]));
        const cr = ratio(fg, bg), need = size >= 24 ? 3 : 4.5;
        if (cr < need) out.issues.push({kind: 'contrast', message: `“${label(t)}” has low contrast (${cr.toFixed(1)}:1; needs ${need}:1).`}); }
    }
    // inside the box it belongs to (a card, pill or panel)
    for (let b = el; b && b !== slide; b = b.parentElement) {
      if (b.classList.contains('slide-body') || !(b instanceof HTMLElement) || !hasBox(b)) continue;
      const br = b.getBoundingClientRect();
      if (r.left < br.left - 1 || r.right > br.right + 1 || r.top < br.top - 1 || r.bottom > br.bottom + 1)
        out.issues.push({kind: 'overflow', message: `“${label(t)}” doesn't fit inside its box (it spills out by ${Math.round(Math.max(br.left - r.left, r.right - br.right, br.top - r.top, r.bottom - br.bottom))}px). Make the box larger, shorten the text, or wrap it onto two lines.`});
      break;
    }
    const cut = el.closest('[style*="overflow"],.clip');
    if (cut && (cut.scrollWidth > cut.clientWidth + 1 || cut.scrollHeight > cut.clientHeight + 1))
      out.issues.push({kind: 'overflow', message: `Text in a clipped container is cut off near “${label(t)}”.`});
  }

  // text crossing the edge of a drawn shape (SVG slides)
  for (const svg of slide.querySelectorAll('svg')) {
    const shapes = [...svg.querySelectorAll('rect,circle,ellipse')].filter(s => eff(s) > .05 && !s.hasAttribute('data-overlay'));
    for (const t of svg.querySelectorAll('text')) {
      if (eff(t) < .05 || !t.textContent.trim()) continue;
      const tr = t.getBoundingClientRect(), area = tr.width * tr.height;
      for (const s of shapes) { const sr = s.getBoundingClientRect(), o = over(tr, sr);
        if (o.w > 0 && o.h > 0) { const ratio = o.w * o.h / area;
          if (ratio > .04 && ratio < .985 && sr.width * sr.height < 640 * 400)
            out.issues.push({kind: 'overflow', message: `“${label(t.textContent)}” crosses the edge of a box in the drawing.`}); } }
    }
  }

  // overlaps: text over text, and boxes with text over boxes with text
  for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
    const a = nodes[i], b = nodes[j]; if (a.el === b.el) continue;
    const o = over(a.r, b.r); if (o.w > 2 && o.h > 2)
      out.issues.push({kind: 'overlap', message: `“${label(a.t)}” overlaps “${label(b.t)}”.`});
  }
  const boxes = [...slide.querySelectorAll('[data-c]')].filter(e => e instanceof HTMLElement && eff(e) > .05 && hasBox(e) && e.textContent.trim() && !e.hasAttribute('data-overlay'));
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
    const a = boxes[i], b = boxes[j]; if (a.contains(b) || b.contains(a)) continue;
    const o = over(a.getBoundingClientRect(), b.getBoundingClientRect());
    if (o.w > 4 && o.h > 4) out.issues.push({kind: 'overlap', message: `The box “${label(a.textContent)}” overlaps the box “${label(b.textContent)}”.`});
  }
  return out;
}
""" % {"tol": SCALE_TOLERANCE, "l": SAFE[0], "t": SAFE[1], "r": SAFE[2], "b": SAFE[3]}


@dataclasses.dataclass
class Issue:
    slide: str
    step: int                 # 1-based narration step it first appears at
    kind: str
    severity: str             # "error" must be fixed; "warn" is worth a look
    message: str

    def to_dict(self): return dataclasses.asdict(self)


def words_of(text):
    """Words worth comparing: 3+ letters, not contractions (don't, we're)."""
    return [w for w in re.findall(r"[a-z0-9']+", html.unescape(text).lower().replace("’", "'")) if len(w) > 2 and "'" not in w]


def stem(word):
    """A crude stem, so "looks"/"looking"/"looked" match "look" (enough for spotting invented words, not for language)."""
    for suffix in ("ingly", "edly", "ing", "ies", "es", "ed", "ly", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3: return word[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return word


def vocabulary(module, extra=()):
    texts = [module.title, module.subtitle, *module.intro, *extra]
    for s in module.slides: texts += [s.title, s.screen, s.note, *s.say, *s.show]
    return {stem(w) for w in words_of(" ".join(texts))}


def static_issues(slide_id, inner_html, css, banned=()):
    """Things that are never allowed in a design (scripts, outside links, animations) found without rendering."""
    problems = []
    for pattern, why in [
        (r"<\s*script", "scripts aren't allowed"), (r"<\s*(iframe|object|embed|link|meta|base|form|img|video|audio)\b", "that element isn't allowed (draw with HTML and SVG)"),
        (r"\son\w+\s*=", "event handlers aren't allowed"), (r"(?:href|src|xlink:href)\s*=\s*[\"']?\s*(?:https?:)?//", "outside links aren't allowed"),
        (r"url\s*\(", "url() isn't allowed (use gradients and SVG shapes)"), (r"@import|@font-face", "@import and @font-face aren't allowed"),
        (r"@keyframes|\banimation\s*:|animation-name", "animations aren't allowed (reveals use data-c and CSS transitions)"),
        (r"position\s*:\s*fixed", "position:fixed isn't allowed"), (r"javascript:", "javascript: links aren't allowed"),
    ]:
        if re.search(pattern, inner_html + "\n" + css, re.I): problems.append(f"{slide_id}: {why}.")
    for rule in re.findall(r"([^{}]+)\{", css):
        if rule.strip().startswith("@"): continue
        for sel in rule.split(","):
            if not sel.strip().startswith(f"#{slide_id}"):
                problems.append(f"{slide_id}: every CSS selector must start with #{slide_id} (found “{sel.strip()[:40]}”).")
                break
    for term in banned:
        if re.search(rf"\b{re.escape(term)}\b", inner_html, re.I): problems.append(f"{slide_id}: the banned term “{term}” appears on the slide.")
    return problems


def inspect(page_html, module, banned=(), allowed_extra=(), shots=True):
    """Render every step of every slide and measure it. Returns {"issues": [Issue], "shots": {(slide, step): jpeg bytes}, "sizes": {...}}."""
    from playwright.sync_api import sync_playwright
    ids = compose.scene_ids(module)
    chunks = ([module.intro] if module.intro else []) + [s.say for s in module.slides]
    allowed = sorted(compose.TYPE_SCALE.values())
    vocab = vocabulary(module, allowed_extra)
    found, order, shot_map, js_errors, sizes = {}, [], {}, [], {}
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "module.html"; path.write_text(page_html, encoding="utf-8")
        with sync_playwright() as p:
            browser, page = cli.open_page(p, path, 1280)
            page.on("pageerror", lambda e: js_errors.append(str(e)))
            page.evaluate(cli.PAGE_JS, ids)
            page.evaluate("__html2mp4.reset()")
            for si, sid in enumerate(ids):
                for ci in range(len(chunks[si])):
                    page.evaluate(f"__html2mp4.show({si},{ci},0)")
                    page.evaluate("__html2mp4.frame(1000)")                  # let every transition finish
                    m = page.evaluate(MEASURE_JS, [sid, allowed])
                    errs = [i for i in m["issues"]]
                    for k, v in m["sizes"].items(): sizes[float(k)] = sizes.get(float(k), 0) + v
                    for i in errs:
                        key = (sid, i["kind"], i["message"])
                        if key not in found: found[key] = Issue(sid, ci + 1, i["kind"], "error", i["message"]); order.append(key)
                    last = ci == len(chunks[si]) - 1
                    if shots and (errs and (sid, "first") not in shot_map or last):
                        jpeg = page.screenshot(type="jpeg", quality=78, clip={"x": 0, "y": 0, "width": 1280, "height": 720})
                        if errs and (sid, "first") not in shot_map: shot_map[(sid, "first")] = (ci + 1, jpeg)
                        if last: shot_map[(sid, "last")] = (ci + 1, jpeg)
                    # words that appear on screen but nowhere in the script (a hint of invented content)
                    for t in m["texts"]:
                        odd = [w for w in words_of(t) if stem(w) not in vocab and w not in STOPWORDS and not w.isdigit()]
                        if odd:
                            key = (sid, "invented", t)
                            if key not in found:
                                found[key] = Issue(sid, ci + 1, "invented", "warn", f"“{t[:50]}” uses words that aren't in your script ({', '.join(odd[:4])}). Check it's accurate.")
                                order.append(key)
            browser.close()
    issues = [found[k] for k in order]
    for e in js_errors: issues.append(Issue("", 0, "script", "error", f"The page has a script error: {e[:160]}"))
    for term in banned:
        if re.search(rf"\b{re.escape(term)}\b", page_html, re.I) and not any(re.search(rf"\b{re.escape(term)}\b", t, re.I) for t in [module.title, *module.intro]):
            issues.append(Issue("", 0, "banned", "error", f"The banned term “{term}” appears in the module."))
    return {"issues": issues, "shots": shot_map, "sizes": sizes}
