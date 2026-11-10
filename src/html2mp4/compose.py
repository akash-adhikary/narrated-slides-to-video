"""Assemble a narrated module (a single HTML file) from a script outline.

The composer owns everything that must be exactly right: the stage, the brand theme, the narration list (taken
verbatim from the script), each slide's wrapper and footer, and a small review player. Slide *content* comes either
from the basic layout here or from a designer (see design.py), as inner HTML plus CSS.
"""
import html, json, re
from html2mp4 import __version__

STAGE_W, STAGE_H = 1280, 720
# The only font sizes (px) a slide may use, so every module looks uniform. Footer text is exempt.
TYPE_SCALE = {"display": 96, "title": 64, "heading": 44, "lead": 28, "body": 22, "small": 16}
esc = html.escape


def slug(name): return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "colour"


def palette_names(brand):
    """[(css name, colour)] for each brand colour; the name is what follows --c- in the CSS variable."""
    seen, out = set(), []
    for c in brand.get("palette", []):
        n = slug(re.sub(r"\(.*?\)", "", c["name"]))
        if n in seen: n = f"{n}-{c['hex'][1:].lower()}"
        seen.add(n); out.append((n, c))
    return out


def palette_vars(brand):
    """--c-<name>: one CSS variable per brand colour (e.g. --c-cyan-spot), for the slide designer."""
    return "".join(f"--c-{n}:{c['hex']};" for n, c in palette_names(brand))


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
    return _theme(brand) + MOTION_CSS + PLAYER_CSS


def _theme(brand):
    return f""":root{{
  --bg:{brand['background']}; --text:{brand['text']}; --accent:{brand['accent']}; --accent2:{brand['accent2']};
  --muted:color-mix(in srgb, var(--text) 64%, var(--bg)); --faint:color-mix(in srgb, var(--text) 38%, var(--bg));
  --surface:color-mix(in srgb, var(--text) 6%, var(--bg)); --surface2:color-mix(in srgb, var(--text) 10%, var(--bg));
  --line:color-mix(in srgb, var(--text) 16%, var(--bg)); --accent-soft:color-mix(in srgb, var(--accent) 18%, var(--bg));
  --hfont:"{brand['heading_font']}", system-ui, -apple-system, "Segoe UI", sans-serif;
  --bfont:"{brand['body_font']}", system-ui, -apple-system, "Segoe UI", sans-serif;
  {"".join(f"--fs-{k}:{v}px;" for k, v in TYPE_SCALE.items())}
  {palette_vars(brand)}
}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{height:100%;background:#000;overflow:hidden}}
#frame{{position:fixed;inset:0 0 70px 0;display:flex;align-items:center;justify-content:center}}
#stage{{width:{STAGE_W}px;height:{STAGE_H}px;flex:none;position:relative;overflow:hidden;background:var(--bg);color:var(--text);
  font-family:var(--bfont);transform-origin:center center}}
.slide{{position:absolute;inset:0;opacity:0;visibility:hidden;transform:scale(1.025);transition:opacity .7s ease,transform 1s cubic-bezier(.2,.7,.2,1)}}
.slide.active{{opacity:1;visibility:visible;transform:none}}
.slide-body{{position:absolute;left:80px;right:80px;top:64px;bottom:96px}}
[data-c]{{opacity:0;transform:translateY(14px);transition:opacity .7s ease var(--d,0s), transform .7s cubic-bezier(.2,.7,.2,1) var(--d,0s), filter .7s ease var(--d,0s), clip-path .8s cubic-bezier(.4,0,.2,1) var(--d,0s)}}
[data-c].on{{opacity:1;transform:none;filter:none}}
h1,h2,h3{{font-family:var(--hfont);font-weight:600;letter-spacing:-.02em;line-height:1.1}}
.slide-foot{{position:absolute;left:80px;right:80px;bottom:30px;height:32px;display:flex;align-items:center;justify-content:space-between;
  font:500 13px var(--bfont);color:var(--faint);letter-spacing:.02em}}
.slide-foot img{{height:32px;width:auto;display:block}}
.dots{{display:flex;gap:6px}} .dots i{{width:6px;height:6px;border-radius:50%;background:var(--line)}} .dots i.on{{background:var(--accent)}}

/* design kit: building blocks for slide designs (all sizes come from the type scale) */
.t-display{{font:500 var(--fs-display)/1 var(--hfont);letter-spacing:-.03em}}
.t-title{{font:600 var(--fs-title)/1.08 var(--hfont);letter-spacing:-.025em}}
.t-heading{{font:600 var(--fs-heading)/1.12 var(--hfont);letter-spacing:-.02em}}
.t-lead{{font:500 var(--fs-lead)/1.25 var(--hfont);letter-spacing:-.01em}}
.t-body{{font:400 var(--fs-body)/1.4 var(--bfont)}}
.t-small{{font:500 var(--fs-small)/1.3 var(--bfont)}}
.t-eyebrow{{font:600 var(--fs-small)/1.2 var(--bfont);letter-spacing:.16em;text-transform:uppercase;color:var(--accent)}}
.t-muted{{color:var(--muted)}}
.stack{{display:flex;flex-direction:column;gap:24px}}
.row{{display:flex;gap:24px;align-items:stretch}}
.row > *{{flex:1;min-width:0}}
.grid{{display:grid;gap:24px}}
.card{{background:var(--surface);border:1px solid var(--line);border-radius:20px;padding:28px}}
.pill{{display:inline-block;padding:6px 16px;border-radius:999px;background:var(--accent-soft);color:var(--accent);font:600 var(--fs-small)/1.2 var(--bfont)}}

/* title slide */
.title-slide .slide-body{{display:flex;flex-direction:column;justify-content:center}}
.title-slide .eyebrow{{font:600 var(--fs-small) var(--bfont);letter-spacing:.16em;text-transform:uppercase;color:var(--accent);margin-bottom:22px}}
.title-slide h1{{font-size:var(--fs-title);max-width:960px}}
.title-slide .rule{{width:120px;height:4px;border-radius:2px;background:linear-gradient(90deg,var(--accent),var(--accent2));margin-top:34px}}
.title-slide .glow{{position:absolute;right:-160px;top:-160px;width:620px;height:620px;border-radius:50%;
  background:radial-gradient(circle,var(--accent-soft),transparent 68%);animation:h2m-drift 16s ease-in-out infinite}}

/* basic layout */
.basic h2{{font-size:var(--fs-heading);max-width:1000px}}
.basic h2::before{{content:"";display:block;width:56px;height:4px;border-radius:2px;background:var(--accent);margin-bottom:26px}}
.basic .slide-body{{display:flex;flex-direction:column}}
.basic .cards{{margin:auto 0;display:grid;gap:22px}}
.basic .cards.n1{{grid-template-columns:1fr}} .basic .cards.n2{{grid-template-columns:repeat(2,1fr)}}
.basic .cards.n3,.basic .cards.n5,.basic .cards.n6{{grid-template-columns:repeat(3,1fr)}} .basic .cards.n4{{grid-template-columns:repeat(2,1fr)}}
.basic .card{{background:var(--surface);border:1px solid var(--line);border-radius:20px;padding:32px 32px;min-height:196px;display:flex;flex-direction:column;justify-content:space-between;gap:16px}}
.basic .card b{{font:600 var(--fs-small) var(--bfont);color:var(--accent);letter-spacing:.08em}}
.basic .card span{{font:500 var(--fs-lead)/1.25 var(--hfont);letter-spacing:-.015em}}
.basic .cards.n1 .card span{{font-size:var(--fs-heading)}}
.basic .list{{margin:auto 0;columns:2;column-gap:56px;list-style:none}}
.basic .list li{{break-inside:avoid;font:500 var(--fs-body)/1.35 var(--bfont);padding:14px 0 14px 34px;position:relative;border-top:1px solid var(--line)}}
.basic .list li::before{{content:"";position:absolute;left:0;top:25px;width:12px;height:12px;border-radius:3px;background:var(--accent)}}
.basic.statement .slide-body{{display:flex;align-items:center}}
.basic.statement h2{{font-size:var(--fs-title);max-width:980px}}
"""


# ---------------------------------------------------------------- motion kit
# Everything animated in a module comes from here, so it is tested and the video reproduces it frame for frame: reveals and
# drawing are CSS transitions; the ambient loops are the kit's own keyframes. Designs use these through classes and data-fx;
# they may not write their own keyframes (see verify.static_issues).
MOTION_CSS = """
/* motion kit: entrances (data-fx on an element with data-c; the default is a rise) */
[data-c][data-fx=pop]{transform:scale(.84);transition:opacity .45s ease var(--d,0s), transform .65s cubic-bezier(.34,1.56,.64,1) var(--d,0s)}
[data-c][data-fx=left]{transform:translateX(-56px)}
[data-c][data-fx=right]{transform:translateX(56px)}
[data-c][data-fx=zoom]{transform:scale(1.14)}
[data-c][data-fx=blur]{filter:blur(16px);transform:scale(1.03)}
[data-c][data-fx=wipe]{opacity:1;transform:none;clip-path:inset(-24px 100% -24px -24px)}
[data-c][data-fx].on{opacity:1;transform:none;filter:none}
[data-c][data-fx=wipe].on{clip-path:inset(-24px -24px -24px -24px)}
/* drawing: add class draw and pathLength="1" to an SVG path/line/circle/rect; it traces itself in when its element appears */
.draw{stroke-dasharray:1;stroke-dashoffset:1;transition:stroke-dashoffset var(--draw,1.1s) cubic-bezier(.4,0,.2,1) calc(var(--d,0s) + .12s)}
.on .draw,.draw.on{stroke-dashoffset:0}
/* count-up: <span class="count" style="--to:40"></span> counts from 0 to --to when it appears */
@property --n{syntax:'<integer>';initial-value:0;inherits:false}
.count{--n:0;display:inline-block;font-variant-numeric:tabular-nums;counter-reset:cnt var(--n);transition:--n 1.5s cubic-bezier(.2,.7,.2,1) calc(var(--d,0s) + .15s)}
.count::after{content:counter(cnt)}
.on .count,.count.on{--n:var(--to,0)}
/* emphasis on appearing: highlight sweep under text, glow around a card */
.hl{background:linear-gradient(var(--accent-soft),var(--accent-soft)) no-repeat 0 90%/0% 42%;transition:background-size .8s cubic-bezier(.4,0,.2,1) calc(var(--d,0s) + .35s)}
.on .hl,.hl.on{background-size:100% 42%}
.glow-in{box-shadow:0 0 0 0 transparent;transition:box-shadow 1s ease calc(var(--d,0s) + .3s)}
.on.glow-in,.on .glow-in{box-shadow:0 0 36px 2px color-mix(in srgb,var(--accent) 38%,transparent)}
/* flow: steps in a row (or .down a column) with arrows that draw themselves between them as each step appears */
.flow{display:flex;align-items:stretch;gap:72px}
.flow > *{flex:1;min-width:0;position:relative}
.flow > :not(:first-child)::before{content:"";position:absolute;left:-60px;top:50%;width:44px;height:3px;margin-top:-1.5px;border-radius:2px;
  background:linear-gradient(90deg,var(--accent2),var(--accent));transform:scaleX(0);transform-origin:left;transition:transform .5s cubic-bezier(.4,0,.2,1) calc(var(--d,0s) + .3s)}
.flow > :not(:first-child)::after{content:"";position:absolute;left:-19px;top:50%;margin-top:-8px;border-left:12px solid var(--accent);border-top:8px solid transparent;
  border-bottom:8px solid transparent;opacity:0;transition:opacity .2s ease calc(var(--d,0s) + .75s)}
.flow > .on:not(:first-child)::before{transform:scaleX(1)}
.flow > .on:not(:first-child)::after{opacity:1}
.flow.down{flex-direction:column;gap:64px}
.flow.down > :not(:first-child)::before{left:50%;top:-52px;width:3px;height:36px;margin:0 0 0 -1.5px;transform:scaleY(0);transform-origin:top;
  background:linear-gradient(180deg,var(--accent2),var(--accent))}
.flow.down > :not(:first-child)::after{left:50%;top:-18px;margin:0 0 0 -8px;border-left:8px solid transparent;border-right:8px solid transparent;border-top:12px solid var(--accent);border-bottom:0}
.flow.down > .on:not(:first-child)::before{transform:scaleY(1)}
/* ambient loops: gentle, slow, and always on an inner element (never on the element that has data-c) */
@keyframes h2m-float{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}
@keyframes h2m-pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.07)}}
@keyframes h2m-glow{0%,100%{filter:drop-shadow(0 0 0 transparent)}50%{filter:drop-shadow(0 0 12px color-mix(in srgb,var(--accent) 70%,transparent))}}
@keyframes h2m-flow{to{stroke-dashoffset:-32}}
@keyframes h2m-drift{0%,100%{transform:translate(0,0) scale(1)}50%{transform:translate(36px,-24px) scale(1.1)}}
@keyframes h2m-spin{to{transform:rotate(360deg)}}
.amb-float,.amb-pulse,.amb-drift,.amb-spin{transform-box:fill-box;transform-origin:center}
.amb-float{animation:h2m-float 5s ease-in-out infinite}
.amb-pulse{animation:h2m-pulse 3.6s ease-in-out infinite}
.amb-glow{animation:h2m-glow 3.2s ease-in-out infinite}
.amb-flow{stroke-dasharray:6 10;animation:h2m-flow 1.6s linear infinite}
.amb-drift{animation:h2m-drift 14s ease-in-out infinite}
.amb-spin{animation:h2m-spin 40s linear infinite}
/* a soft light that drifts behind every slide */
#stage::before,#stage::after{content:"";position:absolute;border-radius:50%;pointer-events:none;width:760px;height:760px;animation:h2m-drift 24s ease-in-out infinite}
#stage::before{left:-260px;top:-380px;background:radial-gradient(circle,color-mix(in srgb,var(--accent) 15%,transparent),transparent 66%)}
#stage::after{right:-300px;bottom:-420px;background:radial-gradient(circle,color-mix(in srgb,var(--accent2) 13%,transparent),transparent 66%);animation-delay:-12s}
/* Calm: entrances and slide changes only */
[data-motion=calm] .amb-float,[data-motion=calm] .amb-pulse,[data-motion=calm] .amb-glow,[data-motion=calm] .amb-flow,
[data-motion=calm] .amb-drift,[data-motion=calm] .amb-spin,[data-motion=calm] #stage::before,[data-motion=calm] #stage::after,
[data-motion=calm] .title-slide .glow{animation:none}
@media (prefers-reduced-motion:reduce){.amb-float,.amb-pulse,.amb-glow,.amb-flow,.amb-drift,.amb-spin,#stage::before,#stage::after{animation:none}}
"""

PLAYER_CSS = """
/*h2m:player-css*/
/* review player (hidden in the video) */
#bar{position:fixed;left:0;right:0;bottom:0;height:70px;background:#0b0b0f;color:#e8e8ee;display:flex;align-items:center;gap:8px;padding:6px 14px 0;
  font:14px system-ui,-apple-system,sans-serif;border-top:1px solid #222;transition:transform .3s ease,opacity .3s ease}
#bar button,#bar select{background:#1b1b22;color:inherit;border:1px solid #2c2c36;border-radius:8px;height:36px;min-width:36px;padding:0 10px;cursor:pointer;font:inherit}
#bar select{padding:0 6px;max-width:150px}
#bar button:hover,#bar select:hover{background:#26262f}
#bar button:focus-visible,#bar select:focus-visible,#seek:focus-visible{outline:2px solid #7c83ff;outline-offset:2px}
#bar button[aria-pressed=true]{background:#2c2f6b;border-color:#5b61d6}
#bar button[hidden],#bar select[hidden]{display:none}
#bar .cap{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#b9b9c6;padding:0 6px}
#bar .pos{font-variant-numeric:tabular-nums;color:#8a8a99;min-width:56px;text-align:right}
#bar .note{color:#8a8a99;font-size:12px;white-space:nowrap}
#seek{position:absolute;left:0;right:0;top:-7px;height:14px;cursor:pointer}
#seek .rail{position:absolute;left:0;right:0;top:5px;height:4px;background:#2a2a35}
#seek .fill{position:absolute;left:0;top:5px;height:4px;width:0;background:#7c83ff}
#seek .tick{position:absolute;top:2px;width:2px;height:10px;background:#0b0b0f}
#seek:hover .rail,#seek:hover .fill{top:4px;height:6px}
#capbox{position:fixed;left:50%;transform:translateX(-50%);bottom:84px;max-width:80%;background:rgba(0,0,0,.72);color:#fff;font:500 18px/1.4 system-ui,sans-serif;
  padding:8px 16px;border-radius:10px;text-align:center;pointer-events:none}
#capbox:empty,#capbox[hidden]{display:none}
@media (max-width:900px){#bar .cap,#bar .note{display:none}#bar .spacer{flex:1}}
@media (max-width:620px){#voice{display:none}}
body.full #frame{inset:0}
body.full #bar{position:fixed;background:rgba(11,11,15,.86);border-top:0;backdrop-filter:blur(6px)}
body.full.idle #bar{transform:translateY(100%);opacity:0}
body.full.idle{cursor:none}
body.full #capbox{bottom:96px;font-size:24px}
body.full.idle #capbox{bottom:28px}
#notice{position:fixed;left:50%;transform:translateX(-50%);bottom:130px;max-width:86%;background:#2c2f6b;color:#fff;font:500 14px/1.4 system-ui,sans-serif;
  padding:9px 16px;border-radius:10px;text-align:center;box-shadow:0 6px 24px rgba(0,0,0,.4)}
#notice[hidden]{display:none}
body.full #notice{bottom:110px}
/*h2m:end*/
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
    # a point that is spoken in a sentence appears on those words; the others are spread across the narration
    spoken_in = [next((j for j, say in enumerate(slide.say) if _contains(say, x)), None) for x in items]
    cue = [sp if sp is not None else min(n - 1, i * n // len(items)) for i, sp in enumerate(spoken_in)]
    stagger = [0 if spoken_in[i] is not None else sum(1 for j in range(i) if cue[j] == cue[i]) * 0.25 + (0.3 if cue[i] == 0 else 0)
               for i in range(len(items))]
    attrs = [f'data-c="{c}"' + (f' data-cue="{esc(x)}"' if sp is not None else "") + (f' data-d="{d:g}"' if d else "")
             for x, c, d, sp in zip(items, cue, stagger, spoken_in)]
    if len(items) <= 6 and all(len(x) <= 60 for x in items):
        cards = "".join(f'<div class="card" {a}><b>{i + 1:02}</b><span>{esc(x)}</span></div>' for i, (x, a) in enumerate(zip(items, attrs)))
        body = f'<div class="cards n{len(items)}">{cards}</div>'
    else:
        body = '<ul class="list">' + "".join(f'<li {a}>{esc(x)}</li>' for x, a in zip(items, attrs)) + "</ul>"
    return "basic", f'<h2 data-c="0">{esc(slide.title)}</h2>{body}'


PLAYER_JS = r"""/*h2m:player-js*/
(function(){
  var flat = [], LEAD = 0.25;                       // a word-timed graphic starts this early, so it is readable as the word is heard
  scenes.forEach(function(s, si){ s.chunks.forEach(function(t, ci){ flat.push([si, ci, t]); }); });
  var pos = 0, playing = false, token = 0, timers = [], rate = 1, mode = 'browser', audio = null, studio = null, cued = [], nextAudio = null, retries = 0;
  var $ = function(id){ return document.getElementById(id); };
  var stage = $('stage'), bar = $('bar'), cap = bar.querySelector('.cap'), count = bar.querySelector('.pos'), play = $('play'), capbox = $('capbox');
  var q = new URLSearchParams(location.search), STUDIO = q.get('studio'), VERSION = q.get('v');
  var voiceSel = $('voice'), voice = null, ccOn = false;
  function store(k, v){ try { if (v === undefined) return localStorage.getItem('h2m-' + k); localStorage.setItem('h2m-' + k, v); } catch (e) {} return null; }
  function norm(w){ return w.toLowerCase().replace(/[^a-z0-9]+/g, ''); }
  function wordsOf(text){ var out = [], re = /\S+/g, m; while ((m = re.exec(text))) { var n = norm(m[0]); if (n) out.push([n, m.index]); } return out; }
  function cueIndex(e, text){
    var cue = (e.getAttribute('data-cue') || '').split(/\s+/).map(norm).filter(Boolean); if (!cue.length) return -1;
    var w = wordsOf(text);
    for (var i = 0; i + cue.length <= w.length; i++) { var ok = true; for (var k = 0; k < cue.length; k++) if (w[i + k][0] !== cue[k]) { ok = false; break; } if (ok) return i; }
    return -1;
  }
  var noticeEl = $('notice'), noticeTimer = null;
  function notice(text, ms){ clearTimeout(noticeTimer); noticeEl.textContent = text || ''; noticeEl.hidden = !text; if (text && ms) noticeTimer = setTimeout(function(){ notice(''); }, ms); }
  function clearTimers(){ timers.forEach(clearTimeout); timers = []; }
  function stopAudio(){ try { if (window.speechSynthesis) speechSynthesis.cancel(); } catch (e) {} if (audio) { audio.onended = audio.onerror = null; audio.pause(); audio = null; } }
  function dropPreload(){ if (nextAudio) { nextAudio.onerror = null; nextAudio = null; } }

  // ---- what is on screen at a step. live = while narrating: cued things wait for their word; otherwise they use an estimate.
  // A sentence that brings one graphic shows it as the sentence starts. Only a sentence that names several things in turn
  // ("easy, medium and hard") reveals each on its word. (The video follows the same rule.)
  function listed(si, ci){                        // several different cue phrases in one sentence (two parts of one graphic sharing a cue are one thing)
    var seen = {}; [].forEach.call(document.getElementById(scenes[si].id).querySelectorAll('[data-cue]'), function(e){ if (+e.dataset.c === ci) seen[norm(e.getAttribute('data-cue'))] = 1; });
    return Object.keys(seen).length > 1;
  }
  function showStep(live){
    var si = flat[pos][0], ci = flat[pos][1], text = flat[pos][2], many = listed(si, ci); cued = [];
    scenes.forEach(function(s, i){
      var el = document.getElementById(s.id); el.classList.toggle('active', i === si);
      el.querySelectorAll('[data-c]').forEach(function(e){
        var c = +e.dataset.c, d = parseFloat(e.getAttribute('data-d') || 0), now = i < si || (i === si && c <= ci);
        var isCued = i === si && c === ci && e.hasAttribute('data-cue') && many;
        if (live && isCued) { cued.push(e); e.classList.remove('on'); if (d) e.style.setProperty('--d', d + 's'); else e.style.removeProperty('--d'); return; }
        if (!live && isCued) { var k = cueIndex(e, text); if (k > 0) d += Math.max(0, k * 0.4 - LEAD); }
        if (d) e.style.setProperty('--d', d + 's'); else e.style.removeProperty('--d');
        e.classList.toggle('on', now);
      });
    });
    ui();
  }
  function reveal(e){ e.classList.add('on'); var i = cued.indexOf(e); if (i >= 0) cued.splice(i, 1); }
  function revealAll(){ cued.slice().forEach(reveal); }
  function ui(){
    cap.textContent = flat[pos][2]; capbox.textContent = ccOn ? flat[pos][2] : ''; capbox.hidden = !ccOn;
    count.textContent = (pos + 1) + ' / ' + flat.length; $('seekfill').style.width = ((pos + 1) / flat.length * 100) + '%';
    play.textContent = playing ? 'Pause' : 'Play';
    try { parent.postMessage({html2mp4: 'step', pos: pos, total: flat.length}, '*'); } catch (e) {}
  }

  // ---- narrating
  function after(my){
    var next = flat[pos + 1], leaving = next && next[0] !== flat[pos][0], h = scenes[flat[pos][0]].hold;
    var gap = 450 + (leaving ? 700 + 1000 * (h != null ? h : (window.__h2mHold || 0)) : 0);     // a slide's own Hold: wins over the Studio's pacing
    timers.push(setTimeout(function(){ if (token !== my || !playing) return; if (pos >= flat.length - 1) { pause(); return; } pos++; playStep(); }, gap / rate));
  }
  function armEstimate(text, my, factor){        // when no word timing is available: appear after about 0.42 s per word
    cued.slice().forEach(function(e){
      var k = cueIndex(e, text); e._char = k > 0 ? wordsOf(text)[k][1] : 0;
      if (k <= 0) { reveal(e); return; }
      timers.push(setTimeout(function(){ if (token === my) reveal(e); }, Math.max(0, k * 0.42 - LEAD) / rate * 1000 * factor));
    });
  }
  function speakBrowser(my){
    var text = flat[pos][2], u = new SpeechSynthesisUtterance(text);
    if (voice) { u.voice = voice; u.lang = voice.lang; } u.rate = rate;
    u.onboundary = function(ev){ if (token !== my) return; var ch = ev.charIndex || 0; cued.slice().forEach(function(e){ if (ch >= e._char) reveal(e); }); };
    u.onend = function(){ if (token !== my) return; revealAll(); after(my); };
    u.onerror = function(ev){ if (token !== my || ev.error === 'interrupted' || ev.error === 'canceled') return; revealAll(); after(my); };
    speechSynthesis.cancel(); try { speechSynthesis.resume(); } catch (e) {} speechSynthesis.speak(u);
  }
  function preload(){                              // fetch the next sentence while this one plays, so there is no wait between them
    var n = flat[pos + 1]; if (!n || !studio) { dropPreload(); return; }
    var url = studio.urls[n[0]][n[1]]; if (nextAudio && nextAudio._url === url) return;
    var a = new Audio(url); a.preload = 'auto'; a._url = url; nextAudio = a;
  }
  function playStudio(my){
    var si = flat[pos][0], ci = flat[pos][1], url = studio.urls[si][ci], words = (studio.times[si] || [])[ci] || [];
    if (nextAudio && nextAudio._url === url && !nextAudio.error) { audio = nextAudio; nextAudio = null; } else { dropPreload(); audio = new Audio(url); }
    var a = audio, started = false, watchdog = null;
    a.playbackRate = rate; a.preservesPitch = a.webkitPreservesPitch = true;
    cued.forEach(function(e){
      var cue = (e.getAttribute('data-cue') || '').split(/\s+/).map(norm).filter(Boolean), at = 0;
      for (var i = 0; i + cue.length <= words.length; i++) { var ok = true; for (var k = 0; k < cue.length; k++) if (words[i + k][0] !== cue[k]) { ok = false; break; } if (ok) { at = Math.max(0, words[i][1] - LEAD); break; } }
      e._at = at;
    });
    a.addEventListener('playing', function(){ started = true; retries = 0; clearTimeout(watchdog); });
    a.onended = function(){ if (token !== my) return; revealAll(); after(my); };
    a.onerror = function(){ if (token === my) studioFailed(my); };
    watchdog = setTimeout(function(){ if (token === my && !started) studioFailed(my); }, window.__h2mWatchdogMs || 7000); timers.push(watchdog);   // never wait forever for a sound that isn't coming
    var pr = a.play();
    if (pr && pr.catch) pr.catch(function(err){
      if (token !== my) return;
      if (err && err.name === 'NotAllowedError') { pause(); notice('Your browser blocked the sound. Press Play to start it.', 7000); }
      else if (!err || err.name !== 'AbortError') studioFailed(my);
    });
    preload();
    (function loop(){ if (token !== my) return; var t = audio ? audio.currentTime : 0; cued.slice().forEach(function(e){ if (t >= e._at) reveal(e); }); requestAnimationFrame(loop); })();
  }
  // The studio voice stopped working (for example the Studio restarted): say so, reconnect once, and carry on from this sentence.
  function studioFailed(my){
    if (token !== my) return;
    token++; clearTimers(); stopAudio(); dropPreload();
    if (retries >= 1) { retries = 0; giveUp(); return; }
    retries++; studio = null; reconnect(0);
  }
  // A restart of the Studio takes a few seconds, so keep trying for a while before giving up on the studio voice.
  function reconnect(n){
    notice('The studio voice was interrupted. Reconnecting' + (n ? ' (try ' + (n + 1) + ' of 5)' : '') + '…');
    prepareStudio(true).then(function(){ if (playing) playStep(); }, function(e){
      if (e && e.message === 'cancelled') { if (playing) playStep(); return; }
      if (n >= 4) giveUp(); else setTimeout(function(){ reconnect(n + 1); }, 1800);
    });
  }
  function giveUp(){
    studio = null; setStudio(false);
    notice("The studio voice isn't available right now, so your browser's voice is being used. Press Studio voice to try again.", 9000);
    if (playing) playStep();
  }
  function playStep(){
    token++; var my = token; clearTimers(); stopAudio(); showStep(true);
    var text = flat[pos][2];
    if (mode === 'studio' && studio) return playStudio(my);
    if (window.speechSynthesis && voice) { armEstimate(text, my, 1.7); return speakBrowser(my); }
    armEstimate(text, my, 1);                                                  // no voices available: silent, paced by reading speed
    timers.push(setTimeout(function(){ if (token === my) { revealAll(); after(my); } }, (text.split(/\s+/).length / 2.5 + 0.8) / rate * 1000));
  }
  function pause(){ playing = false; token++; clearTimers(); stopAudio(); ui(); }
  function resume(){ playing = true; if (pos >= flat.length - 1 && !cued.length) pos = 0; playStep(); }
  function go(i){ pos = Math.max(0, Math.min(flat.length - 1, i)); if (playing) playStep(); else { token++; clearTimers(); stopAudio(); showStep(false); } }

  play.onclick = function(){ if (playing) pause(); else resume(); };
  $('prev').onclick = function(){ go(pos - 1); };
  $('next').onclick = function(){ go(pos + 1); };
  var seek = $('seek');
  scenes.forEach(function(s, si){ var first = flat.findIndex(function(f){ return f[0] === si; }); if (first > 0) { var t = document.createElement('i'); t.className = 'tick'; t.style.left = (first / flat.length * 100) + '%'; seek.appendChild(t); } });
  seek.onclick = function(ev){ var r = seek.getBoundingClientRect(); go(Math.floor((ev.clientX - r.left) / r.width * flat.length)); };
  $('speed').onchange = function(){ rate = parseFloat(this.value); store('rate', this.value); if (audio) audio.playbackRate = rate; if (playing) playStep(); };
  var saved = store('rate'); if (saved) { $('speed').value = saved; rate = parseFloat(saved) || 1; }
  $('cc').onclick = function(){ ccOn = !ccOn; this.setAttribute('aria-pressed', ccOn); store('cc', ccOn ? '1' : '0'); ui(); };
  if (store('cc') === '1') { ccOn = true; $('cc').setAttribute('aria-pressed', 'true'); }

  // ---- the browser's own voice (a preview: the video uses the studio voice)
  function loadVoices(){
    if (!window.speechSynthesis) { voiceSel.hidden = true; return; }
    var all = speechSynthesis.getVoices().filter(function(v){ return /^en/i.test(v.lang); });
    if (!all.length) { voiceSel.hidden = true; return; }
    var prefer = [/natural|neural|online/i, /Google US English/i, /Samantha|Ava|Allison|Aria|Jenny|Daniel/i, /en[-_]US/i];
    var rank = function(v){ for (var i = 0; i < prefer.length; i++) if (prefer[i].test(v.name) || prefer[i].test(v.lang)) return i; return 9; };
    all.sort(function(a, b){ return rank(a) - rank(b) || a.name.localeCompare(b.name); });
    var want = store('voice');
    voice = all.filter(function(v){ return v.name === want; })[0] || all[0];
    voiceSel.innerHTML = ''; all.forEach(function(v){ var o = document.createElement('option'); o.value = v.name; o.textContent = v.name.replace(/^(Microsoft|Google)\s+/, ''); voiceSel.appendChild(o); });
    voiceSel.value = voice.name; voiceSel.hidden = false;
  }
  voiceSel.onchange = function(){ voice = speechSynthesis.getVoices().filter(function(v){ return v.name === voiceSel.value; })[0] || voice; store('voice', voiceSel.value); if (playing && mode === 'browser') playStep(); };
  if (window.speechSynthesis) { loadVoices(); speechSynthesis.onvoiceschanged = loadVoices; } else voiceSel.hidden = true;

  // ---- the studio voice (only when this page is open inside the Studio, which can make it)
  var sv = $('studiovoice'), preparing = null, cancelPrep = null, base = STUDIO ? '/api/projects/' + encodeURIComponent(STUDIO) : '';
  function setStudio(on, label){ mode = on ? 'studio' : 'browser'; sv.setAttribute('aria-pressed', on); sv.textContent = label || 'Studio voice'; voiceSel.disabled = on; if (!on) dropPreload(); }
  function showPrep(s){ sv.textContent = s.total ? 'Preparing ' + s.done + '/' + s.total : 'Preparing…'; notice(s.label + (playing && mode !== 'studio' ? ' Meanwhile your browser voice is playing.' : '')); }
  function prepareStudio(quiet){
    if (preparing) return preparing;
    var cancelled = false, timer = null; sv.textContent = 'Preparing…';
    preparing = new Promise(function(resolve, reject){
      cancelPrep = function(){ cancelled = true; clearTimeout(timer); reject(new Error('cancelled')); };
      var json = function(r){ return r.json().then(function(j){ if (!r.ok) throw new Error(j.detail || 'failed'); return j; }); };
      function finish(s){ studio = s; resolve(); }
      function poll(id){
        if (cancelled) return;
        fetch('/api/narration/' + id).then(json).then(function(s){
          if (cancelled) return;
          if (s.status === 'failed') throw new Error(s.error || 'failed');
          if (s.status === 'done') return finish(s);
          showPrep(s); timer = setTimeout(function(){ poll(id); }, 600);
        }).catch(function(e){ if (!cancelled) reject(e); });
      }
      fetch(base + '/narration' + (VERSION ? '?v=' + encodeURIComponent(VERSION) : ''), {method: 'POST'}).then(json).then(function(j){
        if (cancelled) return;
        if (j.ready) finish(j.ready); else poll(j.id);
      }).catch(function(e){ if (!cancelled) reject(e); });
    }).then(function(){ preparing = null; cancelPrep = null; setStudio(true); notice(''); },
            function(e){
              preparing = null; cancelPrep = null; var byUser = e && e.message === 'cancelled';
              if (!quiet || byUser) setStudio(false);                                  // while reconnecting, keep the studio voice selected until we give up
              if (byUser) notice(''); else if (!quiet) notice('The studio voice could not be prepared: ' + (e && e.message || e), 9000);
              throw e; });
    return preparing;
  }
  if (STUDIO) {
    sv.hidden = false; sv.title = 'Hear the same voice the video will use';
    sv.onclick = function(){
      if (preparing) { cancelPrep(); return; }                                        // click again while preparing to cancel
      if (mode === 'studio') { setStudio(false); notice('Using your browser voice' + (playing ? ' from the next sentence.' : '.'), 3000); return; }
      if (studio) { setStudio(true); notice('Studio voice' + (playing ? ' from the next sentence.' : ' on.'), 3000); return; }
      prepareStudio().catch(function(){});                                           // a playing narration keeps going and switches at the next sentence
    };
  }

  // ---- full screen, and a bar that gets out of the way
  var idleTimer = null;
  function awake(){ document.body.classList.remove('idle'); clearTimeout(idleTimer); if (document.body.classList.contains('full')) idleTimer = setTimeout(function(){ document.body.classList.add('idle'); }, 2600); }
  function fullscreen(){
    var d = document, root = d.documentElement;
    if (d.fullscreenElement) { d.exitFullscreen(); return; }
    var r = root.requestFullscreen ? root.requestFullscreen() : null;
    if (r && r.catch) r.catch(function(){ try { parent.postMessage({html2mp4: 'fullscreen'}, '*'); } catch (e) {} });
    else if (!r) { try { parent.postMessage({html2mp4: 'fullscreen'}, '*'); } catch (e) {} }
  }
  $('fs').onclick = fullscreen;
  document.addEventListener('fullscreenchange', function(){ document.body.classList.toggle('full', !!document.fullscreenElement); fit(); awake(); });
  ['mousemove', 'mousedown', 'touchstart'].forEach(function(n){ addEventListener(n, awake); });
  addEventListener('keydown', function(e){
    awake();
    if (e.target && /^(SELECT|INPUT|TEXTAREA)$/.test(e.target.tagName)) return;
    if (e.key === 'ArrowRight') go(pos + 1); else if (e.key === 'ArrowLeft') go(pos - 1);
    else if (e.code === 'Space') { e.preventDefault(); play.click(); }
    else if (e.key === 'f' || e.key === 'F') fullscreen(); else if (e.key === 'c' || e.key === 'C') $('cc').click();
  });
  addEventListener('message', function(e){
    if (!e.data) return;
    if (e.data.html2mp4 === 'go') { pause(); go(e.data.pos); }
    else if (e.data.html2mp4 === 'pause') pause();
  });
  function fit(){
    var h = document.body.classList.contains('full') ? 0 : 70;
    stage.style.transform = 'scale(' + Math.min(innerWidth / __W__, (innerHeight - h) / __H__) + ')';
  }
  addEventListener('resize', fit); fit(); showStep(false);
})();
/*h2m:end*/
""".replace("__W__", str(STAGE_W)).replace("__H__", str(STAGE_H))


PLAYER_BAR_HTML = """<!--h2m:bar--><div id="capbox" hidden></div><div id="notice" role="status" hidden></div>
<div id="bar">
<div id="seek" role="presentation" title="Click to jump"><div class="rail"></div><div class="fill" id="seekfill"></div></div>
<button id="prev" aria-label="Previous step" title="Previous (←)">‹</button><button id="play" title="Play or pause (space)">Play</button><button id="next" aria-label="Next step" title="Next (→)">›</button>
<span class="cap"></span>
<select id="speed" aria-label="Speed" title="Speaking speed"><option value="0.75">0.75×</option><option value="1" selected>1×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option></select>
<select id="voice" aria-label="Voice" title="Your browser's voice (a preview)" hidden></select>
<button id="studiovoice" hidden aria-pressed="false">Studio voice</button>
<button id="cc" aria-pressed="false" title="Captions (C)">CC</button>
<button id="fs" aria-label="Full screen" title="Full screen (F)">⤢</button>
<span class="pos"></span></div><!--/h2m:bar-->"""

PROJECT_RE = re.compile(r'(<script type="application/json" id="html2mp4-project">)(.*?)(</script>)', re.S)
FONTS_RE = re.compile(r'<style id="html2mp4-fonts">.*?</style>\n?|<link[^>]*fonts\.(?:googleapis|gstatic)\.com[^>]*>\n?', re.S)


PLAYER_PARTS = (re.compile(r"<!--h2m:bar-->.*?<!--/h2m:bar-->\n?", re.S), re.compile(r"/\*h2m:player-css\*/.*?/\*h2m:end\*/", re.S),
                re.compile(r"/\*h2m:player-js\*/.*?/\*h2m:end\*/", re.S))


HOLD_RE = re.compile(r'<script id="h2m-hold">.*?</script>\n?', re.S)


def with_hold(page, seconds):
    """Tell the page's player how long to hold every finished slide, from the Studio's pacing setting (a slide's own Hold: still wins).
    Applied when the page is shown or downloaded, so changing the setting needs no redesign."""
    page = HOLD_RE.sub("", page)
    if not seconds or "</head>" not in page: return page
    return page.replace("</head>", f'<script id="h2m-hold">window.__h2mHold={float(seconds):g};</script>\n</head>', 1)


def fingerprint(page):
    """A hash of the page without its project block, its font links or its player, so a file can tell whether it was edited after the
    Studio made it (and still match after fonts are embedded for download or the player is brought up to date)."""
    import hashlib
    page = HOLD_RE.sub("", FONTS_RE.sub("", PROJECT_RE.sub(r"\1\3", page)))
    for part in PLAYER_PARTS: page = part.sub("", page)
    return hashlib.sha256(page.encode()).hexdigest()


def _marked(text, start, end="/*h2m:end*/"): return text[text.index(start): text.index(end) + len(end)]


def refresh_player(page):
    """Bring a module made by the Studio up to the current player (full screen, voices, fixes). Only the player is replaced: the slides are
    untouched, and a file that isn't one of ours is returned as it is. Older modules are recognised by their layout."""
    if 'name="generator" content="html2mp4' not in page: return page
    clean = (read_project(page) or {}).get("edited") is False
    css, js = _marked(PLAYER_CSS, "/*h2m:player-css*/"), _marked(PLAYER_JS, "/*h2m:player-js*/")
    out = page
    if "<!--h2m:bar-->" in out:
        out = PLAYER_PARTS[0].sub(lambda m: PLAYER_BAR_HTML + "\n", out, count=1)
        out = PLAYER_PARTS[1].sub(lambda m: css, out, count=1)
        out = PLAYER_PARTS[2].sub(lambda m: js, out, count=1)
    else:                                                                            # made before the player had markers
        out = out.replace('<div id="capbox" hidden></div>\n', "")
        out = re.sub(r'<div id="bar">.*?<span class="(?:count|pos)"></span></div>', lambda m: PLAYER_BAR_HTML, out, count=1, flags=re.S)
        out, n = re.subn(r"/\* review player \(hidden in the video\) \*/.*?body\.full\.idle #capbox\{[^}]*\}\n?", lambda m: css + "\n", out, count=1, flags=re.S)
        if not n: out = re.sub(r"/\* review player \(hidden in the video\) \*/.*?#bar \.count\{[^}]*\}\n?", lambda m: css + "\n", out, count=1, flags=re.S)
        out = re.sub(r"\(function\(\)\{\n  var flat = \[\];.*\}\)\(\);\n", lambda m: js + "\n", out, count=1, flags=re.S)
        out = out.replace("#frame{position:fixed;inset:0 0 64px 0;", "#frame{position:fixed;inset:0 0 70px 0;")
    if clean and out != page and PROJECT_RE.search(out):                              # a file the Studio wrote and nobody changed stays "unedited"
        data = json.loads(PROJECT_RE.search(out).group(2)); data["fingerprint"] = fingerprint(out)
        enc = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
        out = PROJECT_RE.sub(lambda m: m.group(1) + enc + m.group(3), out, count=1)
    return out


def read_project(page):
    """The project data embedded in a module made by the Studio ({"script", "slides", ...}), or None. Adds "edited": whether the page
    was changed after the Studio wrote it."""
    m = PROJECT_RE.search(page)
    if not m or not m.group(2).strip(): return None
    try: data = json.loads(m.group(2))
    except ValueError: return None
    if not isinstance(data, dict) or not isinstance(data.get("script"), str): return None
    data["edited"] = data.get("fingerprint") != fingerprint(page)
    return data


def assemble(module, brand, slides, css="", motion="lively", project=None):
    """Build the module document. `slides` is a list of (layout_class, inner_html), one per content slide.
    `project` (script text, slide designs...) is embedded so the file can be opened again as an editable project."""
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
    holds = ([None] if module.intro else []) + [s.hold for s in module.slides]
    scene_js = ",\n".join(f"  {{id:'{sid}', {f'hold:{h:g}, ' if h is not None else ''}chunks:{json.dumps(c, ensure_ascii=False)}}}" for sid, c, h in zip(ids, chunks, holds))
    scene_js = scene_js.replace("</", "<\\/")
    source = json.dumps(module.to_dict(), ensure_ascii=False).replace("</", "<\\/")
    faces, covered = font_faces(brand)
    page = f"""<!DOCTYPE html>
<html lang="en" data-motion="{'calm' if motion == 'calm' else 'lively'}">
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
{PLAYER_BAR_HTML}
<script type="application/json" id="html2mp4-source">{source}</script>
<script type="application/json" id="html2mp4-project"></script>
<script>
var scenes = [
{scene_js}
];
{PLAYER_JS}
</script>
</body>
</html>
"""
    if project is not None:
        data = json.dumps({**project, "fingerprint": fingerprint(page), "generator": f"html2mp4 {__version__}"}, ensure_ascii=False).replace("</", "<\\/")
        page = PROJECT_RE.sub(lambda m: m.group(1) + data + m.group(3), page, count=1)
    return page


def embed_fonts(page, fetch=None):
    """Make a module work offline: the Google Fonts it links to are fetched once and embedded. If anything fails the page is returned unchanged."""
    import base64, urllib.request
    link = re.search(r'<link[^>]*href="(https://fonts\.googleapis\.com/css2\?[^"]+)"[^>]*>', page)
    if not link: return page
    def get(url, ua=False):
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"} if ua else {})
        with urllib.request.urlopen(req, timeout=12) as r: return r.read()
    fetch = fetch or get
    try:
        css = fetch(link.group(1).replace("&amp;", "&"), True).decode()
        def inline(m):
            data = fetch(m.group(1))
            return f"url(data:font/woff2;base64,{base64.b64encode(data).decode()})"
        css = re.sub(r"url\((https://fonts\.gstatic\.com/[^)]+)\)", inline, css)
    except Exception:
        return page
    page = re.sub(r'<link[^>]*fonts\.(?:googleapis|gstatic)\.com[^>]*>\n?', "", page)
    return page.replace("<style>", f'<style id="html2mp4-fonts">\n{css}\n</style>\n<style>', 1)


def basic_module(module, brand, motion="lively", script_text=None):
    """A complete module using the built-in layout (no AI)."""
    project = {"script": script_text, "slides": None, "brand": brand.get("kit_name", "")} if script_text is not None else None
    return assemble(module, brand, [basic_slide(s) for s in module.slides], motion=motion, project=project)


def _cue_words(text): return [w for w in (re.sub(r"[^a-z0-9]+", "", x.lower()) for x in text.split()) if w]


def _contains(sentence, phrase):
    words, cue = _cue_words(sentence), _cue_words(phrase)
    return any(words[i:i + len(cue)] == cue for i in range(len(words) - len(cue) + 1))


class _Reveals(__import__("html.parser", fromlist=["HTMLParser"]).HTMLParser):
    """Collects, per slide, every element's data-c / data-cue (any quoting style)."""
    def __init__(self):
        super().__init__(convert_charrefs=True); self.slides, self.current = {}, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "section" and a.get("id"): self.current = a["id"]; self.slides[self.current] = []
        elif self.current and "data-c" in a: self.slides[self.current].append((a["data-c"], a.get("data-cue")))

    def handle_endtag(self, tag):
        if tag == "section": self.current = None


def check_detailed(html_text, module):
    """Problems that would make the module unusable for video, as [(slide id or "", message)]; empty when fine."""
    from html2mp4.cli import load_scenes, ConversionError
    try:
        scenes = load_scenes(html_text)
    except ConversionError as e:
        return [("", str(e))]
    problems = []
    expected = ([module.intro] if module.intro else []) + [s.say for s in module.slides]
    if [s["chunks"] for s in scenes] != expected:
        problems.append(("", "The narration in the page doesn't match the script."))
    parser = _Reveals(); parser.feed(html_text)
    for sid, chunks in zip(scene_ids(module), expected):
        reveals = parser.slides.get(sid)
        if reveals is None: problems.append((sid, f"Slide {sid} is missing.")); continue
        steps = {int(c) for c, _ in reveals if str(c).isdigit()}
        bad = sorted(c for c in steps if c >= len(chunks))
        if bad: problems.append((sid, f"Slide {sid} reveals content on narration step {bad[0]}, but it only has steps 0 to {len(chunks) - 1}."))
        if 0 not in steps: problems.append((sid, f"Slide {sid} shows nothing with its first sentence (step 0): the heading needs data-c=\"0\"."))
        for c, cue in reveals:
            if cue and str(c).isdigit() and int(c) < len(chunks) and _cue_words(cue) and not _contains(chunks[int(c)], cue):
                problems.append((sid, f"Slide {sid}: the cue “{cue}” isn't in narration step {c}; copy the words exactly from that sentence."))
    return problems


def check(html_text, module):
    return [m for _, m in check_detailed(html_text, module)]


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
