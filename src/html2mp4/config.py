"""User settings: the Anthropic API key and the brand kit.

Settings live in ~/.config/html2mp4/settings.json (override with HTML2MP4_CONFIG), not in the cache, so clearing the
cache never loses them. The file is written with owner-only permissions because it can hold an API key.
"""
import json, os, pathlib, re

CONFIG_DIR = pathlib.Path(os.environ.get("HTML2MP4_CONFIG", pathlib.Path.home() / ".config" / "html2mp4"))
SETTINGS_FILE = CONFIG_DIR / "settings.json"

DESIGN_MODEL = "claude-opus-5-5"     # designs slides from scripts

FONTS = ["Inter", "Geist", "IBM Plex Sans", "Source Sans 3", "Poppins", "DM Sans", "Merriweather", "Lora"]
STYLES = ("dark", "light")

DEFAULT_BRAND = {
    "style": "dark",                 # dark or light slides
    "background": "#0f1222",         # slide background
    "text": "#f4f5fa",               # main text
    "accent": "#7c83ff",             # headings, highlights, progress
    "accent2": "#3dd6c6",            # secondary highlight
    "heading_font": "Inter",
    "body_font": "Inter",
    "footer_text": "",
    "logo_on_dark": "",              # data URI of a light-coloured logo, used on dark slides
    "logo_on_light": "",             # data URI of a dark logo, used on light slides
    "logo": "",                      # older single-logo setting; used when the two above are empty
    # filled by importing a brand kit (brandkit.py); passed to the slide designer
    "palette": [],                   # [{name, hex, group, usage}]
    "rules": [],                     # design rules from the guidelines
    "kit_name": "",
    "reference": "",                 # file name of the module used as a style reference
}
BUNDLED = pathlib.Path(__file__).parent / "defaults" / "thoughtspot"   # the brand a fresh install starts with


def default_brand():
    """The brand a fresh install starts with: the bundled ThoughtSpot kit, or the neutral one if HTML2MP4_BRAND=neutral."""
    if os.environ.get("HTML2MP4_BRAND") == "neutral": return dict(DEFAULT_BRAND)
    try: return {**DEFAULT_BRAND, **json.loads((BUNDLED / "brand.json").read_text())["brand"]}
    except (OSError, ValueError, KeyError): return dict(DEFAULT_BRAND)


def install_default_fonts():
    """Copy the bundled typefaces into the config folder once, so they are available like any imported kit font."""
    src, dst = BUNDLED / "fonts", CONFIG_DIR / "fonts"
    if os.environ.get("HTML2MP4_BRAND") == "neutral" or not (src / "fonts.json").exists() or (dst / "fonts.json").exists(): return
    try:
        dst.mkdir(parents=True, exist_ok=True)
        for f in src.iterdir(): (dst / f.name).write_bytes(f.read_bytes())
    except OSError: pass


KIT_FIELDS = ("palette", "rules", "kit_name", "reference", "logo", "logo_on_dark", "logo_on_light")
LOGO_MAX_BYTES = 512 * 1024


def load():
    try:
        data = json.loads(SETTINGS_FILE.read_text())
    except (FileNotFoundError, ValueError):
        data = {}
    if "brand" not in data: install_default_fonts()
    data["brand"] = {**default_brand(), **data["brand"]} if "brand" in data else default_brand()
    return data


def save(data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = SETTINGS_FILE.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, SETTINGS_FILE)


# ---------------------------------------------------------------- API key

def api_key():
    """The key to use: one saved in Settings wins over ANTHROPIC_API_KEY. None lets the SDK resolve credentials
    itself (ANTHROPIC_AUTH_TOKEN or an `ant auth login` profile)."""
    return load().get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY") or None


def api_key_status():
    saved = load().get("anthropic_api_key")
    key, source = (saved, "settings") if saved else (os.environ.get("ANTHROPIC_API_KEY"), "environment")
    if not key: return {"set": False, "source": None, "masked": None}
    return {"set": True, "source": source, "masked": f"{key[:7]}…{key[-4:]}" if len(key) > 14 else "set"}


def set_api_key(key):
    data = load(); data["anthropic_api_key"] = key.strip(); save(data)


def clear_api_key():
    data = load(); data.pop("anthropic_api_key", None); save(data)


# ---------------------------------------------------------------- design quality

DESIGN_EFFORTS = {"balanced": "medium", "thorough": "high"}     # how hard Claude thinks when designing slides


def design_quality(): return load().get("design_quality", "balanced")


def set_design_quality(value):
    if value not in DESIGN_EFFORTS: raise ValueError("design quality must be balanced or thorough")
    data = load(); data["design_quality"] = value; save(data)


def design_effort(): return DESIGN_EFFORTS.get(design_quality(), "medium")


# ---------------------------------------------------------------- motion

MOTIONS = ("lively", "calm")


def motion(): return load().get("motion", "lively")


def set_motion(value):
    if value not in MOTIONS: raise ValueError("motion must be lively or calm")
    data = load(); data["motion"] = value; save(data)


# ---------------------------------------------------------------- glossary

DEFAULT_GLOSSARY = {"pronunciations": {}, "banned": [], "approved": []}


def default_pronunciations():
    if os.environ.get("HTML2MP4_BRAND") == "neutral": return {}
    try: return dict(json.loads((BUNDLED / "brand.json").read_text()).get("pronunciations", {}))
    except (OSError, ValueError): return {}


def glossary():
    """Pronunciations ({written: spoken}), banned terms (the designer must not use them) and approved terms.
    Until the glossary is first saved, pronunciations start from the bundled brand's list."""
    saved = load().get("glossary")
    g = saved or {}
    out = {k: g.get(k, v) for k, v in DEFAULT_GLOSSARY.items()}
    if saved is None: out["pronunciations"] = default_pronunciations()
    return out


def set_glossary(changes):
    g = glossary()
    if "pronunciations" in changes:
        g["pronunciations"] = {str(k).strip(): str(v).strip() for k, v in dict(changes["pronunciations"]).items() if str(k).strip() and str(v).strip()}
    for k in ("banned", "approved"):
        if k in changes: g[k] = [str(x).strip() for x in changes[k] if str(x).strip()]
    data = load(); data["glossary"] = g; save(data)
    return g


# ---------------------------------------------------------------- brand

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def brand():
    return load()["brand"]


def update_brand(changes):
    """Validate and save brand fields; unknown fields are ignored. Returns the full brand."""
    b = brand()
    for k, v in changes.items():
        if k not in DEFAULT_BRAND or k in KIT_FIELDS: continue
        if k in ("background", "text", "accent", "accent2"):
            if not HEX.match(str(v)): raise ValueError(f"{k} must be a colour like #1a2b3c")
        elif k in ("heading_font", "body_font"):
            if v not in available_fonts(): raise ValueError(f"{k} must be one of: {', '.join(available_fonts())}")
        elif k == "style":
            if v not in STYLES: raise ValueError("style must be dark or light")
        elif k == "footer_text":
            v = str(v)[:80]
        b[k] = v
    data = load(); data["brand"] = b; save(data)
    return b


def available_fonts():
    """Fonts installed from a brand kit first, then the built-in Google Fonts choices."""
    try: custom = [f["family"] for f in json.loads((CONFIG_DIR / "fonts" / "fonts.json").read_text())]
    except (FileNotFoundError, ValueError): custom = []
    return custom + [f for f in FONTS if f not in custom]


def set_logo(data_uri, slot="logo_on_dark"):
    data = load(); data["brand"][slot] = data_uri; save(data)


def logo_for(b):
    """The logo for this brand's slide style."""
    return (b.get("logo_on_dark") if b.get("style", "dark") == "dark" else b.get("logo_on_light")) or b.get("logo", "")


def reset_brand():
    data = load(); data["brand"] = default_brand(); save(data)
    (CONFIG_DIR / "reference.html").unlink(missing_ok=True)
    return data["brand"]
