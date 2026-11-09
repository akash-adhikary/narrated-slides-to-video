"""Import a brand kit: a guidelines PDF, logo files, font files and/or an existing module (HTML).

analyze() looks at whatever was dropped in and returns a *proposal* (palette, colours for dark and light slides,
fonts, logos, design rules, a style reference); nothing is saved until apply() is called with the person's choices.
Staged files live in the cache; applied fonts, logos and the reference live in the user's config directory.
"""
import base64, colorsys, io, json, pathlib, re, shutil, time, uuid, zipfile
from html import unescape

from html2mp4 import cli, config

STAGING = cli.CACHE / "brandkit"
IMAGE = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
FONT = (".ttf", ".otf", ".woff", ".woff2")
HEX = re.compile(r"#[0-9a-fA-F]{6}\b")
LIGHT_WORDS = ("white", "light", "reverse", "reversed", "knockout", "negative", "inverse", "on-dark", "ondark")
DARK_WORDS = ("black", "dark", "positive", "on-light", "onlight", "navy")


def font_dir(): return config.CONFIG_DIR / "fonts"


def reference_file(): return config.CONFIG_DIR / "reference.html"


# ---------------------------------------------------------------- reading the inputs

def expand(files):
    """[(path, bytes)] with zips unpacked; junk (.DS_Store, __MACOSX, hidden files) dropped."""
    out = []
    for name, data in files:
        if name.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                out += expand([(i.filename, z.read(i)) for i in z.infolist() if not i.is_dir()])
            continue
        parts = pathlib.PurePosixPath(name).parts
        if any(p.startswith((".", "__MACOSX")) for p in parts): continue
        out.append((name, data))
    return out


def luminance(hex_):
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def saturation(hex_):
    return colorsys.rgb_to_hls(*(int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5)))[2]


def logo_tone(name, data):
    """'light' for a light-coloured logo (for dark slides), 'dark' for a dark one (for light slides)."""
    words = re.split(r"[^a-z]+", name.lower())
    if any(w in words for w in LIGHT_WORDS): return "light"
    if any(w in words for w in DARK_WORDS): return "dark"
    try:
        if name.lower().endswith(".svg"):
            fills = HEX.findall(data.decode("utf-8", "ignore"))
            if fills: return "light" if sum(luminance(f) for f in fills) / len(fills) > 0.5 else "dark"
            return "dark"
        from PIL import Image
        im = Image.open(io.BytesIO(data)).convert("RGBA")
        im.thumbnail((128, 128))
        px = [(r, g, b) for r, g, b, a in im.getdata() if a > 128]
        if px: return "light" if sum(0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in px) / len(px) / 255 > 0.5 else "dark"
    except Exception:  # noqa: BLE001 — an unreadable image just gets the default
        pass
    return "dark"


def read_logo(name, data, idx):
    path = pathlib.PurePosixPath(name)
    lower = name.lower()
    kind = "icon" if "icon" in lower or "mark" in lower else "stacked" if "stack" in lower else "primary"
    return {"id": f"logo{idx}", "name": path.name, "path": name, "tone": logo_tone(name, data), "kind": kind,
            "format": path.suffix.lower().lstrip("."), "bytes": len(data),
            "data_uri": f"data:{IMAGE[path.suffix.lower()]};base64,{base64.b64encode(data).decode()}"}


def read_font(name, data):
    from fontTools.ttLib import TTFont
    f = TTFont(io.BytesIO(data))
    names = f["name"]
    family = (names.getDebugName(16) or names.getDebugName(1) or pathlib.PurePosixPath(name).stem).strip()
    italic = bool(f["OS/2"].fsSelection & 1) if "OS/2" in f else "italic" in name.lower()
    if "fvar" in f:
        axis = next((a for a in f["fvar"].axes if a.axisTag == "wght"), None)
        weight = f"{int(axis.minValue)} {int(axis.maxValue)}" if axis else "400"
        variable = True
    else:
        weight, variable = str(f["OS/2"].usWeightClass if "OS/2" in f else 400), False
    return {"family": family, "file": pathlib.PurePosixPath(name).name, "weight": weight, "italic": italic, "variable": variable}


def read_pdf(data):
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(data))
    return "\n".join(f"--- page {i + 1} ---\n{p.extract_text() or ''}" for i, p in enumerate(r.pages[:60]))[:60000]


def read_module(text):
    """Palette, fonts and logos declared by an existing module, plus a compact copy to use as a style reference."""
    palette, fonts, logos = [], [], []
    root = re.search(r":root\s*\{(.*?)\}", text, re.S)
    if root:
        for name, value in re.findall(r"--([\w-]+)\s*:\s*(#[0-9a-fA-F]{6})\b", root.group(1)):
            palette.append({"name": name.replace("-", " ").title(), "hex": value.upper(), "group": "module", "usage": f"--{name} in the module"})
    for fam in re.findall(r"font-family\s*:\s*['\"]([^'\"]+)['\"]", text) + re.findall(r"--[\w-]+\s*:\s*['\"]([^'\"]+)['\"]\s*,", text):
        if fam not in fonts and not fam.startswith(("ui-", "SF ")): fonts.append(fam)
    for var, uri in re.findall(r"--([\w-]+)\s*:\s*url\(\s*['\"]?(data:image/[^'\")]+)", text):
        mime, b64 = uri[5:].split(";base64,", 1)
        data = base64.b64decode(b64)
        ext = {"image/svg+xml": ".svg", "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}.get(mime, ".png")
        logos.append((f"module/{var}{ext}", data))
    compact = re.sub(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=]{200,}", "data:,", text)      # drop embedded images and fonts
    return palette, fonts, logos, compact


# ---------------------------------------------------------------- proposing a kit

AI_SCHEMA = {
    "type": "object",
    "properties": {
        "kit_name": {"type": "string"},
        "palette": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "hex": {"type": "string"},
            "group": {"type": "string", "enum": ["primary", "secondary", "tertiary", "other"]},
            "usage": {"type": "string"}}, "required": ["name", "hex", "group", "usage"], "additionalProperties": False}},
        "dark": {"$ref": "#/$defs/roles"}, "light": {"$ref": "#/$defs/roles"},
        "heading_font": {"type": "string"}, "body_font": {"type": "string"},
        "rules": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["kit_name", "palette", "dark", "light", "heading_font", "body_font", "rules"],
    "additionalProperties": False,
    "$defs": {"roles": {"type": "object", "properties": {k: {"type": "string"} for k in ("background", "text", "accent", "accent2")},
                        "required": ["background", "text", "accent", "accent2"], "additionalProperties": False}},
}

AI_SYSTEM = """You turn brand guidelines into a brand kit for designing narrated training slides (1280×720, shown as video).
Use only colours whose hex codes appear in the guidelines. Name each colour as the guidelines do.
Choose a dark-slide set and a light-slide set (background, text, accent, accent2) that follow the guidelines' usage
advice and give body text at least 4.5:1 contrast. Pick the heading and body typefaces the guidelines specify.
Write `rules` as short, concrete instructions a slide designer must follow: typography treatments (case, weights,
gradients), how colours and gradients are used, logo usage and clear space, accessibility. Leave out anything that
doesn't apply to slides (print, swag, merchandise)."""


def heuristic(palette, fonts_found):
    """Pick dark and light role colours without AI: the darkest and lightest colours, and the most vivid accents."""
    hexes = [p["hex"] for p in palette] or ["#0F1222", "#F4F5FA", "#7C83FF", "#3DD6C6"]
    # prefer a brand's own near-black / near-white over pure #000000 / #FFFFFF
    darks = [h for h in hexes if luminance(h) < 0.03]
    lights = [h for h in hexes if luminance(h) > 0.85]
    dark_bg = next((h for h in darks if h != "#000000"), None) or min(hexes, key=luminance)
    light_bg = "#FFFFFF" if "#FFFFFF" in lights else (max(lights, key=luminance) if lights else max(hexes, key=luminance))
    vivid = sorted((h for h in hexes if h not in (dark_bg, light_bg)), key=saturation, reverse=True) or ["#7C83FF", "#3DD6C6"]
    pick = lambda bg: [h for h in vivid if contrast(h, bg) >= 3] or vivid
    da, la = pick(dark_bg), pick(light_bg)
    return {
        "dark": {"background": dark_bg, "text": light_bg, "accent": da[0], "accent2": (da[1:] or da)[0]},
        "light": {"background": light_bg, "text": dark_bg, "accent": la[0], "accent2": (la[1:] or la)[0]},
        "heading_font": fonts_found[0] if fonts_found else "Inter",
        "body_font": fonts_found[-1] if fonts_found else "Inter",
    }


def analyze(files, use_ai=True):
    """Look at the dropped files and return a proposal (also staged on disk for apply())."""
    from html2mp4 import ai
    files = expand(files)
    pid = uuid.uuid4().hex[:12]
    stage = STAGING / pid; (stage / "fonts").mkdir(parents=True)
    pdf_text, palette, families, logos, notes, reference, module_fonts = "", [], {}, [], [], None, []
    top = {pathlib.PurePosixPath(n).parts[0] for n, _ in files if len(pathlib.PurePosixPath(n).parts) > 1}
    kit_name = next(iter(top)) if len(top) == 1 else ""

    for name, data in files:
        ext = pathlib.PurePosixPath(name).suffix.lower()
        if ext == ".pdf":
            pdf_text += read_pdf(data) + "\n"
        elif ext in IMAGE:
            if len(data) <= config.LOGO_MAX_BYTES: logos.append(read_logo(name, data, len(logos)))
            else: notes.append(f"Skipped {pathlib.PurePosixPath(name).name}: larger than 512 KB.")
        elif ext in FONT:
            try:
                info = read_font(name, data)
            except Exception:  # noqa: BLE001
                notes.append(f"Couldn't read the font {pathlib.PurePosixPath(name).name}."); continue
            (stage / "fonts" / info["file"]).write_bytes(data)
            families.setdefault(info["family"], []).append(info)
        elif ext in (".html", ".htm"):
            pal, mfonts, mlogos, compact = read_module(data.decode("utf-8", "ignore"))
            palette += pal; module_fonts += mfonts
            logos += [read_logo(n, d, len(logos) + i) for i, (n, d) in enumerate(mlogos)]
            (stage / "reference.html").write_text(compact)
            reference = {"name": pathlib.PurePosixPath(name).name, "kb": round(len(compact) / 1024)}

    # per family, a variable font replaces its static files
    fonts = []
    for fam, infos in sorted(families.items()):
        var = [i for i in infos if i["variable"]]
        fonts.append({"family": fam, "files": var or infos, "variable": bool(var)})
    font_names = [f["family"] for f in fonts] + [f for f in module_fonts if f not in families]

    used_ai = False
    proposal = None
    if pdf_text and use_ai and ai.available():
        try:
            data, usage = ai.structured(AI_SYSTEM, f"Brand guidelines (extracted text):\n\n{pdf_text}"
                                        + (f"\n\nFont files provided: {', '.join(font_names)}" if font_names else ""),
                                        AI_SCHEMA, effort="medium", max_tokens=16000)
            seen = {h.upper() for h in HEX.findall(pdf_text)}
            data["palette"] = [p for p in data["palette"] if p["hex"].upper() in seen]
            proposal, used_ai = data, True
            notes.append(f"Claude read the guidelines (about ${ai.cost(usage):.2f}).")
        except ai.AIError as e:
            notes.append(f"Couldn't read the guidelines with Claude ({e}); used a basic scan instead.")
    if pdf_text and not used_ai:
        lines = pdf_text.splitlines()
        for i, line in enumerate(lines):
            for h in HEX.findall(line):
                prev = next((l.strip() for l in reversed(lines[max(0, i - 2):i]) if l.strip() and not HEX.search(l)), "")
                palette.append({"name": prev[:30] or h.upper(), "hex": h.upper(), "group": "other", "usage": ""})
        font_names += [f for f in config.FONTS if re.search(rf"\b{re.escape(f)}\b", pdf_text, re.I) and f not in font_names]

    # one entry per colour, guideline names first
    merged, seen = [], set()
    for p in (proposal["palette"] if proposal else []) + palette:
        h = p["hex"].upper()
        if h not in seen: seen.add(h); merged.append({**p, "hex": h})
    picks = proposal or heuristic(merged, font_names)
    for side in ("dark", "light"):
        picks[side] = {k: v.upper() for k, v in picks[side].items()}

    def best(tone):
        cands = [l for l in logos if l["tone"] == tone]
        cands.sort(key=lambda l: (l["kind"] != "primary", l["format"] != "svg", "module/" in l["path"]))
        return cands[0]["id"] if cands else ""

    result = {
        "id": pid, "kit_name": (proposal or {}).get("kit_name") or kit_name or (reference or {}).get("name", ""),
        "palette": merged, "dark": picks["dark"], "light": picks["light"],
        "heading_font": picks.get("heading_font") or (font_names[0] if font_names else "Inter"),
        "body_font": picks.get("body_font") or (font_names[-1] if font_names else "Inter"),
        "fonts": fonts, "font_names": font_names,
        "logos": logos, "logo_on_dark": best("light"), "logo_on_light": best("dark"),
        "rules": (proposal or {}).get("rules", []), "reference": reference,
        "sources": {"pdf": bool(pdf_text), "logos": len(logos), "fonts": len(fonts), "module": bool(reference), "ai": used_ai},
        "notes": notes,
    }
    (stage / "proposal.json").write_text(json.dumps(result))
    for old in STAGING.iterdir():                      # tidy proposals older than a day
        if old.is_dir() and old.name != pid and time.time() - old.stat().st_mtime > 86400: shutil.rmtree(old, ignore_errors=True)
    return result


# ---------------------------------------------------------------- applying

def custom_fonts():
    try: return json.loads((font_dir() / "fonts.json").read_text())
    except (FileNotFoundError, ValueError): return []


def apply(pid, choices):
    """Save the chosen kit: fonts, logos, palette, rules, reference and the brand settings. Returns the brand."""
    stage = STAGING / re.sub(r"\W", "", pid)
    try:
        p = json.loads((stage / "proposal.json").read_text())
    except FileNotFoundError:
        raise ValueError("That brand kit preview has expired. Drop the files in again.")
    style = choices.get("style", "dark")
    roles = {k: choices.get(k) or p[style][k] for k in ("background", "text", "accent", "accent2")}

    # fonts: install the kit's font files, replacing earlier versions of the same families
    registry = [f for f in custom_fonts() if f["family"] not in {x["family"] for x in p["fonts"]}]
    font_dir().mkdir(parents=True, exist_ok=True)
    for fam in p["fonts"]:
        for f in fam["files"]: shutil.copy2(stage / "fonts" / f["file"], font_dir() / f["file"])
        registry.append(fam)
    (font_dir() / "fonts.json").write_text(json.dumps(registry, indent=1))

    by_id = {l["id"]: l for l in p["logos"]}
    logo = lambda key: by_id.get(choices.get(key, p[key]), {}).get("data_uri", "")
    use_ref = choices.get("use_reference", True) and p["reference"]
    if use_ref: shutil.copy2(stage / "reference.html", reference_file())
    b = config.brand()
    b.update(style=style, **roles,
             heading_font=choices.get("heading_font") or p["heading_font"], body_font=choices.get("body_font") or p["body_font"],
             logo_on_dark=logo("logo_on_dark"), logo_on_light=logo("logo_on_light"), logo="",
             palette=[{k: c[k] for k in ("name", "hex", "group", "usage")} for c in p["palette"]],
             rules=p["rules"], kit_name=p["kit_name"], reference=p["reference"]["name"] if use_ref else "")
    data = config.load(); data["brand"] = b; config.save(data)
    return b


def remove_kit():
    """Forget the imported palette, rules and style reference (installed fonts stay available)."""
    data = config.load()
    data["brand"].update(palette=[], rules=[], kit_name="", reference="")
    config.save(data)
    reference_file().unlink(missing_ok=True)
    return data["brand"]
