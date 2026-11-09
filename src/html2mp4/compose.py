"""Assemble a narrated module (a single HTML file) from a script outline.

The composer owns everything that must be exactly right: the stage, the brand theme, the narration list (taken
verbatim from the script), each slide's wrapper and footer, and a small review player. Slide *content* comes either
from the basic layout here or from a designer (see design.py), as inner HTML plus CSS.
"""
import html, json, re
from html2mp4 import __version__

STAGE_W, STAGE_H = 1280, 720
esc = html.escape


def scene_ids(module):
    """s0 is the title slide (only when it has narration); content slides follow."""
    ids = ["s0"] if module.intro else []
    return ids + [f"s{i + 1}" for i in range(len(module.slides))]


def font_faces(brand):
    """Brand-kit fonts embedded as @font-face (exact and offline); returns (css, families covered)."""
    import base64
    from html2mp4 import config
    try: registry = json.loads((config.CONFIG_DIR / "fonts" / "fonts.json").read_text())
    except (FileNotFoundError, ValueError): return "", set()
    wanted = {brand["heading_font"], brand["body_font"]}
    css, covered = [], set()
    for fam in registry:
        if fam["family"] not in wanted: continue
        for f in fam["files"]:
            path = config.CONFIG_DIR / "fonts" / f["file"]
            if not path.exists(): continue
            fmt = {".woff2": "woff2", ".woff": "woff", ".otf": "opentype"}.get(path.suffix.lower(), "truetype")
            mime = {"woff2": "font/woff2", "woff": "font/woff", "opentype": "font/otf"}.get(fmt, "font/ttf")
            css.append(f'@font-face{{font-family:"{fam["family"]}";src:url(data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}) '
                       f'format("{fmt}");font-weight:{f["weight"]};font-style:{"italic" if f.get("italic") else "normal"};font-display:block}}')
            covered.add(fam["family"])
    return "\n".join(css), covered


def fonts_link(brand, covered=()):
    fams = sorted({brand["heading_font"], brand["body_font"]} - set(covered))
    if not fams: return ""
    q = "&".join(f"family={f.replace(' ', '+')}:wght@400;500;600;700" for f in fams)
    return f'<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>' \
           f'<link href="https://fonts.googleapis.com/css2?{q}&display=swap" rel="stylesheet">'


def theme_css(brand):
    return f""":root{{
  --bg:{brand['background']}; --text:{brand['text']}; --accent:{brand['accent']}; --accent2:{brand['accent2']};
  --muted:color-mix(in srgb, var(--text) 64%, var(--bg)); --faint:color-mix(in srgb, var(--text) 38%, var(--bg));
  --surface:color-mix(in srgb, var(--text) 6%, var(--bg)); --surface2:color-mix(in srgb, var(--text) 10%, var(--bg));
  --line:color-mix(in srgb, var(--text) 16%, var(--bg)); --accent-soft:color-mix(in srgb, var(--accent) 18%, var(--bg));
  --hfont:"{brand['heading_font']}", system-ui, -apple-system, "Segoe UI", sans-serif;
  --bfont:"{brand['body_font']}", system-ui, -apple-system, "Segoe UI", sans-serif;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{height:100%;background:#000;overflow:hidden}}
#frame{{position:fixed;inset:0 0 64px 0;display:flex;align-items:center;justify-content:center}}
#stage{{width:{STAGE_W}px;height:{STAGE_H}px;flex:none;position:relative;overflow:hidden;background:var(--bg);color:var(--text);
  font-family:var(--bfont);transform-origin:center center}}
.slide{{position:absolute;inset:0;opacity:0;visibility:hidden;transition:opacity .6s ease}}
.slide.active{{opacity:1;visibility:visible}}
.slide-body{{position:absolute;left:80px;right:80px;top:64px;bottom:96px}}
[data-c]{{opacity:0;transform:translateY(12px);transition:opacity .7s ease var(--d,0s), transform .7s cubic-bezier(.2,.7,.2,1) var(--d,0s)}}
[data-c].on{{opacity:1;transform:none}}
h1,h2,h3{{font-family:var(--hfont);font-weight:600;letter-spacing:-.02em;line-height:1.1}}
.slide-foot{{position:absolute;left:80px;right:80px;bottom:36px;height:24px;display:flex;align-items:center;justify-content:space-between;
  font:500 13px var(--bfont);color:var(--faint);letter-spacing:.02em}}
.slide-foot img{{height:26px;width:auto;display:block}}
.dots{{display:flex;gap:6px}} .dots i{{width:6px;height:6px;border-radius:50%;background:var(--line)}} .dots i.on{{background:var(--accent)}}

/* title slide */
.title-slide .slide-body{{display:flex;flex-direction:column;justify-content:center}}
.title-slide .eyebrow{{font:600 15px var(--bfont);letter-spacing:.16em;text-transform:uppercase;color:var(--accent);margin-bottom:22px}}
.title-slide h1{{font-size:68px;max-width:960px}}
.title-slide .rule{{width:120px;height:4px;border-radius:2px;background:linear-gradient(90deg,var(--accent),var(--accent2));margin-top:34px}}
.title-slide .glow{{position:absolute;right:-160px;top:-160px;width:620px;height:620px;border-radius:50%;
  background:radial-gradient(circle,var(--accent-soft),transparent 68%)}}

/* basic layout */
.basic h2{{font-size:46px;max-width:1000px}}
.basic h2::before{{content:"";display:block;width:56px;height:4px;border-radius:2px;background:var(--accent);margin-bottom:26px}}
.basic .slide-body{{display:flex;flex-direction:column}}
.basic .cards{{margin:auto 0;display:grid;gap:22px}}
.basic .cards.n1{{grid-template-columns:1fr}} .basic .cards.n2{{grid-template-columns:repeat(2,1fr)}}
.basic .cards.n3,.basic .cards.n5,.basic .cards.n6{{grid-template-columns:repeat(3,1fr)}} .basic .cards.n4{{grid-template-columns:repeat(2,1fr)}}
.basic .card{{background:var(--surface);border:1px solid var(--line);border-radius:20px;padding:32px 32px;min-height:196px;display:flex;flex-direction:column;justify-content:space-between;gap:16px}}
.basic .card b{{font:600 14px var(--bfont);color:var(--accent);letter-spacing:.08em}}
.basic .card span{{font:500 28px/1.25 var(--hfont);letter-spacing:-.015em}}
.basic .cards.n1 .card span{{font-size:34px}}
.basic .list{{margin:auto 0;columns:2;column-gap:56px;list-style:none}}
.basic .list li{{break-inside:avoid;font:500 24px/1.35 var(--bfont);padding:14px 0 14px 34px;position:relative;border-top:1px solid var(--line)}}
.basic .list li::before{{content:"";position:absolute;left:0;top:25px;width:12px;height:12px;border-radius:3px;background:var(--accent)}}
.basic.statement .slide-body{{display:flex;align-items:center}}
.basic.statement h2{{font-size:60px;max-width:980px}}

/* review player (hidden in the video) */
#bar{{position:fixed;left:0;right:0;bottom:0;height:64px;background:#0b0b0f;color:#e8e8ee;display:flex;align-items:center;gap:12px;padding:0 16px;
  font:14px system-ui,-apple-system,sans-serif;border-top:1px solid #222}}
#bar button{{background:#1b1b22;color:inherit;border:1px solid #2c2c36;border-radius:8px;height:36px;min-width:36px;padding:0 12px;cursor:pointer;font:inherit}}
#bar button:hover{{background:#26262f}}
#bar .cap{{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#b9b9c6}}
#bar .count{{font-variant-numeric:tabular-nums;color:#8a8a99}}
"""


def _footer(brand, index, total):
    dots = "".join(f'<i class="{"on" if i == index else ""}"></i>' for i in range(total)) if total > 1 else ""
    from html2mp4 import config
    src = config.logo_for(brand)
    logo = f'<img src="{esc(src)}" alt="">' if src else ""
    return f'<div class="slide-foot"><span>{esc(brand.get("footer_text", ""))}</span><div class="dots">{dots}</div>{logo or "<span></span>"}</div>'


def title_slide(module, brand):
    eyebrow = f'<div class="eyebrow" data-c="0">{esc(module.subtitle)}</div>' if module.subtitle else ""
    return (f'<div class="glow"></div><div class="slide-body">{eyebrow}<h1 data-c="0" data-d="0.2">{esc(module.title)}</h1>'
            f'<div class="rule" data-c="0" data-d="0.5"></div></div>')


def basic_slide(slide):
    """Title with the first sentence; on-screen points spread across the narration, in order."""
    n, items = len(slide.say), slide.show
    if not items:
        return "basic statement", f'<h2 data-c="0">{esc(slide.title)}</h2>'
    cue = [min(n - 1, i * n // len(items)) for i in range(len(items))]
    stagger = [sum(1 for j in range(i) if cue[j] == cue[i]) * 0.25 + (0.3 if cue[i] == 0 else 0) for i in range(len(items))]
    attrs = [f'data-c="{c}"' + (f' data-d="{d:g}"' if d else "") for c, d in zip(cue, stagger)]
    if len(items) <= 6 and all(len(x) <= 60 for x in items):
        cards = "".join(f'<div class="card" {a}><b>{i + 1:02}</b><span>{esc(x)}</span></div>' for i, (x, a) in enumerate(zip(items, attrs)))
        body = f'<div class="cards n{len(items)}">{cards}</div>'
    else:
        body = '<ul class="list">' + "".join(f'<li {a}>{esc(x)}</li>' for x, a in zip(items, attrs)) + "</ul>"
    return "basic", f'<h2 data-c="0">{esc(slide.title)}</h2>{body}'


PLAYER_JS = """
(function(){
  var flat = [];
  scenes.forEach(function(s, si){ s.chunks.forEach(function(t, ci){ flat.push([si, ci, t]); }); });
  var pos = 0, timer = null, stage = document.getElementById('stage');
  var cap = document.querySelector('#bar .cap'), count = document.querySelector('#bar .count'), play = document.getElementById('play');
  function render(){
    var si = flat[pos][0], ci = flat[pos][1];
    scenes.forEach(function(s, i){
      var el = document.getElementById(s.id); el.classList.toggle('active', i === si);
      el.querySelectorAll('[data-c]').forEach(function(e){
        var d = e.getAttribute('data-d'); if (d) e.style.setProperty('--d', d + 's');
        e.classList.toggle('on', i < si || (i === si && +e.dataset.c <= ci));
      });
    });
    cap.textContent = flat[pos][2]; count.textContent = (pos + 1) + ' / ' + flat.length;
    try { parent.postMessage({html2mp4: 'step', pos: pos, total: flat.length}, '*'); } catch (e) {}
  }
  function go(i){ pos = Math.max(0, Math.min(flat.length - 1, i)); render(); }
  function stop(){ clearTimeout(timer); timer = null; play.textContent = 'Play'; }
  function tick(){ if (pos >= flat.length - 1) { stop(); return; }
    timer = setTimeout(function(){ go(pos + 1); tick(); }, (flat[pos][2].split(/\\s+/).length / 2.5 + 0.8) * 1000); }
  play.onclick = function(){ if (timer) stop(); else { play.textContent = 'Pause'; if (pos >= flat.length - 1) go(0); tick(); } };
  document.getElementById('prev').onclick = function(){ stop(); go(pos - 1); };
  document.getElementById('next').onclick = function(){ stop(); go(pos + 1); };
  addEventListener('keydown', function(e){
    if (e.key === 'ArrowRight') { stop(); go(pos + 1); } if (e.key === 'ArrowLeft') { stop(); go(pos - 1); }
    if (e.code === 'Space') { e.preventDefault(); play.click(); } });
  addEventListener('message', function(e){ if (e.data && e.data.html2mp4 === 'go') { stop(); go(e.data.pos); } });
  function fit(){ stage.style.transform = 'scale(' + Math.min(innerWidth / %(w)d, (innerHeight - 64) / %(h)d) + ')'; }
  addEventListener('resize', fit); fit(); render();
})();
""" % {"w": STAGE_W, "h": STAGE_H}


def assemble(module, brand, slides, css=""):
    """Build the module document. `slides` is a list of (layout_class, inner_html), one per content slide."""
    ids = scene_ids(module)
    total = len(module.slides)
    sections = []
    if module.intro:
        sections.append(f'<section class="slide title-slide" id="s0">{title_slide(module, brand)}{_footer(brand, -1, 0)}</section>')
    for i, (layout, inner) in enumerate(slides):
        sections.append(f'<section class="slide {esc(layout)}" id="s{i + 1}"><div class="slide-body">{inner}</div>'
                        f'{_footer(brand, i, total)}</section>')
    chunks = ([module.intro] if module.intro else []) + [s.say for s in module.slides]
    # narration verbatim; JSON-encoded, with "</" escaped so it can't end the script block
    scene_js = ",\n".join(f"  {{id:'{sid}', chunks:{json.dumps(c, ensure_ascii=False)}}}" for sid, c in zip(ids, chunks))
    scene_js = scene_js.replace("</", "<\\/")
    source = json.dumps(module.to_dict(), ensure_ascii=False).replace("</", "<\\/")
    faces, covered = font_faces(brand)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="html2mp4 {__version__}">
<title>{esc(module.title)}</title>
{fonts_link(brand, covered)}
<style>
{faces}
{theme_css(brand)}
{css}
</style>
</head>
<body>
<div id="frame"><div id="stage">
{chr(10).join(sections)}
</div></div>
<div id="bar"><button id="prev" aria-label="Previous">‹</button><button id="play">Play</button><button id="next" aria-label="Next">›</button>
<span class="cap"></span><span class="count"></span></div>
<script type="application/json" id="html2mp4-source">{source}</script>
<script>
var scenes = [
{scene_js}
];
{PLAYER_JS}
</script>
</body>
</html>
"""


def basic_module(module, brand):
    """A complete module using the built-in layout (no AI)."""
    return assemble(module, brand, [basic_slide(s) for s in module.slides])


def check(html_text, module):
    """Problems that would make the module unusable for video; empty when it's fine."""
    from html2mp4.cli import load_scenes, ConversionError
    problems = []
    try:
        scenes = load_scenes(html_text)
    except ConversionError as e:
        return [str(e)]
    expected = ([module.intro] if module.intro else []) + [s.say for s in module.slides]
    if [s["chunks"] for s in scenes] != expected:
        problems.append("The narration in the page doesn't match the script.")
    for sid, chunks in zip(scene_ids(module), expected):
        sec = re.search(rf'<section[^>]*\bid="{sid}"[^>]*>(.*?)</section>', html_text, re.S)
        if not sec: problems.append(f"Slide {sid} is missing."); continue
        used = {int(x) for x in re.findall(r'data-c="(\d+)"', sec.group(1))}
        bad = sorted(c for c in used if c >= len(chunks))
        if bad: problems.append(f"Slide {sid} reveals content on narration step {bad[0] + 1}, but it only has {len(chunks)}.")
        if 0 not in used: problems.append(f"Slide {sid} shows nothing with its first sentence.")
    return problems


def main():
    """html2mp4-script: turn a script into a module (HTML)."""
    import argparse, pathlib, sys
    from html2mp4 import config, script
    ap = argparse.ArgumentParser(description="Turn a structured script into a narrated slide module (HTML).")
    ap.add_argument("script", type=pathlib.Path, help="script file (see docs/scripts.md)")
    ap.add_argument("-o", "--out", type=pathlib.Path, help="output .html (default: next to the script)")
    a = ap.parse_args()
    try:
        module = script.parse(a.script.read_text(encoding="utf-8"))
    except script.ScriptError as e:
        sys.exit(f"[html2mp4] error: {e}")
    out = a.out or a.script.with_suffix(".html")
    page = basic_module(module, config.brand())
    problems = check(page, module)
    if problems: sys.exit("[html2mp4] error: " + "; ".join(problems))
    out.write_text(page, encoding="utf-8")
    print(f"[html2mp4] {out}  ({len(module.slides)} slides, {module.sentences} sentences)")
