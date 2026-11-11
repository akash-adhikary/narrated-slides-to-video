"""The media library: images you upload once (mascots, logos, icons, office photos) and use in any module.

    ~/Downloads/Narrated Videos/Media/
        library.json        the items: id, name, kind, description, size, whether it has transparency or is animated
        <id>.png|jpg|webp|svg   the image (an animation is a sprite sheet: its frames side by side)

Uploads are cleaned (orientation fixed, hidden metadata such as GPS dropped, very large images scaled down, SVG checked for scripts).
Edits never overwrite: each makes a new item, so the original stays. Slides use an item with <img data-asset="id">, which is replaced
by the image itself when the page is put together, so a module carries its images wherever it goes and each version keeps the exact
image it was made with.
"""
import base64, html as _html, io, json, os, pathlib, re, threading, time

from PIL import Image, ImageOps

MEDIA = pathlib.Path(os.environ.get("HTML2MP4_MEDIA", pathlib.Path(os.environ.get("HTML2MP4_OUTPUT", pathlib.Path.home() / "Downloads" / "Narrated Videos")) / "Media"))
KINDS = ("mascot", "logo", "icon", "photo", "background", "other")
MAX_SIDE, MAX_UPLOAD, MAX_FRAMES = 2400, 25 * 1024 * 1024, 48
SAM_MODEL = "facebook/sam-vit-base"
_lock = threading.RLock()


class MediaError(ValueError):
    """Something about an image or an edit that the person can act on."""


# ---------------------------------------------------------------- the library

def _index_file(): return MEDIA / "library.json"


def listing():
    try: items = json.loads(_index_file().read_text()).get("items", [])
    except (FileNotFoundError, ValueError): items = []
    return [i for i in items if (MEDIA / i["file"]).exists()]


def _save(items):
    MEDIA.mkdir(parents=True, exist_ok=True)
    tmp = _index_file().with_suffix(".tmp"); tmp.write_text(json.dumps({"items": items}, indent=1)); tmp.replace(_index_file())


def get(ref):
    """An item by id, or by name (ignoring case)."""
    ref = str(ref or "").strip()
    items = listing()
    return next((i for i in items if i["id"] == ref), None) or next((i for i in items if i["name"].casefold() == ref.casefold()), None)


def path(item): return MEDIA / item["file"]


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:48] or "image"


def _unique_id(name, items):
    base, n, taken = slug(name), 2, {i["id"] for i in items}
    out = base
    while out in taken: out, n = f"{base}-{n}", n + 1
    return out


def _unique_name(name, items, exclude=None):
    base, n, taken = name.strip() or "Image", 2, {i["name"].casefold() for i in items if i["id"] != exclude}
    out = base
    while out.casefold() in taken: out, n = f"{base} ({n})", n + 1
    return out


def update(item_id, name=None, kind=None, description=None):
    with _lock:
        items = listing(); it = next((i for i in items if i["id"] == item_id), None)
        if it is None: raise MediaError("That image isn't in the library.")
        if name is not None:
            name = re.sub(r"\s+", " ", name).strip()
            if not name: raise MediaError("Give the image a name.")
            if len(name) > 60: raise MediaError("Keep the name to 60 characters or fewer.")
            if any(i["name"].casefold() == name.casefold() and i["id"] != item_id for i in items): raise MediaError(f"There is already an image called “{name}”.")
            it["name"] = name
        if kind is not None:
            if kind not in KINDS: raise MediaError(f"The kind must be one of: {', '.join(KINDS)}.")
            it["kind"] = kind
        if description is not None: it["description"] = str(description).strip()[:400]
        _save(items); return it


def delete(item_id):
    with _lock:
        items = listing(); it = next((i for i in items if i["id"] == item_id), None)
        if it is None: return
        try: path(it).unlink()
        except FileNotFoundError: pass
        _save([i for i in items if i["id"] != item_id])


# ---------------------------------------------------------------- adding images

SVG_BAD = re.compile(r"<\s*script|\son\w+\s*=|javascript:|<\s*foreignObject|(?:href|src)\s*=\s*[\"']?\s*(?:https?:)?//|<!ENTITY", re.I)


def _svg_size(text):
    w = re.search(r'<svg[^>]*\bwidth\s*=\s*["\']?([\d.]+)', text); h = re.search(r'<svg[^>]*\bheight\s*=\s*["\']?([\d.]+)', text)
    vb = re.search(r'viewBox\s*=\s*["\']\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)', text)
    if vb: return round(float(vb.group(1))), round(float(vb.group(2)))
    if w and h: return round(float(w.group(1))), round(float(h.group(1)))
    return 512, 512


def _has_alpha(im):
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        return im.convert("RGBA").getchannel("A").getextrema()[0] < 250
    return False


def _fit(im):
    if max(im.size) > MAX_SIDE: im = im.copy(); im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    return im


def _encode(im, fmt=None, photo=False):
    """Re-encode (which also drops all hidden metadata). PNG keeps transparency; an opaque photo becomes JPEG."""
    alpha = _has_alpha(im)
    fmt = fmt or ("png" if alpha or not photo else "jpg")
    buf = io.BytesIO()
    if fmt == "jpg": im.convert("RGB").save(buf, "JPEG", quality=90, optimize=True, progressive=True)
    elif fmt == "webp": im.save(buf, "WEBP", quality=92, method=5)
    else: (im if alpha else im.convert("RGB")).save(buf, "PNG", optimize=True)
    return buf.getvalue(), fmt


def _sprite(frames, fmt="webp"):
    """Frames side by side in one image: what a slide animates (with CSS steps, so the video renderer can show any frame exactly)."""
    w, h = frames[0].size
    sheet = Image.new("RGBA", (w * len(frames), h), (0, 0, 0, 0))
    for k, f in enumerate(frames): sheet.paste(f.convert("RGBA").resize((w, h)), (k * w, 0))
    buf = io.BytesIO(); sheet.save(buf, "WEBP", quality=90, method=5)
    return buf.getvalue()


def add(raw, filename="image", name=None, kind=None, description="", parent=None, note=""):
    """Add an uploaded file. Returns the new item."""
    if len(raw) > MAX_UPLOAD: raise MediaError("That file is too large (25 MB at most).")
    stem = re.sub(r"[_\-]+", " ", pathlib.Path(filename).stem).strip() or "Image"
    animated = None
    if raw.lstrip()[:5].lower() in (b"<?xml", b"<svg ") or pathlib.Path(filename).suffix.lower() == ".svg":
        text = raw.decode("utf-8", "replace")
        if "<svg" not in text.lower(): raise MediaError("That doesn't look like an SVG image.")
        if SVG_BAD.search(text): raise MediaError("This SVG contains scripts or outside links, so it can't be used. Export it again as a plain SVG or a PNG.")
        data, fmt, (w, h), alpha = raw, "svg", _svg_size(text), True
    else:
        try: im = Image.open(io.BytesIO(raw)); im.load()
        except Exception: raise MediaError("That file isn't an image this app can read (use PNG, JPG, WebP, GIF or SVG).")
        if getattr(im, "n_frames", 1) > 1:                                   # an animated GIF or WebP: keep it as frames
            frames, durs = [], []
            for k in range(min(im.n_frames, MAX_FRAMES)):
                im.seek(k); frames.append(_fit(im.convert("RGBA"))); durs.append(im.info.get("duration", 80) or 80)
            fps = max(2, min(30, round(1000 / (sum(durs) / len(durs)))))
            data, fmt = _sprite(frames), "webp"; w, h = frames[0].size; alpha = any(_has_alpha(f) for f in frames)
            animated = {"frames": len(frames), "fps": fps, "mode": "loop"}
        else:
            im = _fit(ImageOps.exif_transpose(im))
            if im.mode not in ("RGB", "RGBA"): im = im.convert("RGBA" if _has_alpha(im) else "RGB")
            alpha = _has_alpha(im)
            data, fmt = _encode(im, photo=(im.format or "").upper() != "PNG" and pathlib.Path(filename).suffix.lower() not in (".png", ".gif"))
            w, h = im.size
    return _store(data, fmt, w, h, alpha, name or stem, kind, description, parent, note, animated)


def _store(data, fmt, w, h, alpha, name, kind, description, parent, note, animated=None):
    with _lock:
        items = listing()
        name = _unique_name(name, items)
        iid = _unique_id(name, items)
        MEDIA.mkdir(parents=True, exist_ok=True)
        (MEDIA / f"{iid}.{fmt}").write_bytes(data)
        it = {"id": iid, "name": name, "kind": kind if kind in KINDS else _guess_kind(w, h, alpha), "description": description or "",
              "file": f"{iid}.{fmt}", "format": fmt, "w": w, "h": h, "transparent": bool(alpha), "bytes": len(data),
              "animated": animated, "created": time.time(), "parent": parent, "note": note}
        items.append(it); _save(items)
        return it


def _guess_kind(w, h, alpha):
    if alpha: return "icon" if max(w, h) <= 256 else "other"
    return "photo"


# ---------------------------------------------------------------- reading images back

def image(item, frame=0):
    """The item as a Pillow image (an animation's frame `frame`). SVGs can't be opened this way."""
    if item["format"] == "svg": raise MediaError("SVG images can't be edited here. Convert it to PNG first (open it and export it as PNG).")
    im = Image.open(path(item)); im.load()
    if item.get("animated"):
        w = item["w"]; im = im.crop((frame * w, 0, frame * w + w, item["h"]))
    return im.convert("RGBA") if item["transparent"] else im.convert("RGB")


def frames(item):
    if not item.get("animated"): return [image(item)]
    return [image(item, k) for k in range(item["animated"]["frames"])]


MIME = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp", "svg": "image/svg+xml", "gif": "image/gif"}


def data_uri(item):
    return f"data:{MIME[item['format']]};base64," + base64.b64encode(path(item).read_bytes()).decode()


def export(item, fmt):
    """The image as a file to download, in png, jpg, webp or gif (an animation becomes an animated gif or webp)."""
    fmt = {"jpeg": "jpg"}.get(fmt, fmt)
    if fmt not in ("png", "jpg", "webp", "gif"): raise MediaError("Choose png, jpg, webp or gif.")
    if item["format"] == "svg":
        if fmt != "png": raise MediaError("An SVG can be downloaded as it is, or as PNG.")
        raise MediaError("Converting SVG to PNG isn't available yet. Download the SVG itself.")
    fr = frames(item); buf = io.BytesIO()
    if item.get("animated") and fmt in ("gif", "webp"):
        dur = round(1000 / item["animated"]["fps"])
        if fmt == "gif":
            pal = [_gif_frame(f) for f in fr]
            pal[0].save(buf, "GIF", save_all=True, append_images=pal[1:], duration=dur, loop=0, disposal=2, transparency=0)
        else: fr[0].save(buf, "WEBP", save_all=True, append_images=fr[1:], duration=dur, loop=0, quality=90)
    else:
        im = fr[0]
        if fmt == "jpg": im.convert("RGB").save(buf, "JPEG", quality=92)
        elif fmt == "gif": _gif_frame(im).save(buf, "GIF", transparency=0)
        elif fmt == "webp": im.save(buf, "WEBP", quality=92)
        else: im.save(buf, "PNG")
    return buf.getvalue(), MIME[fmt]


def _gif_frame(im):
    """GIF has on/off transparency only: palette index 0 is see-through, everything else as close as 255 colours allow."""
    im = im.convert("RGBA"); alpha = im.getchannel("A")
    p = im.convert("RGB").quantize(255, method=Image.Quantize.MEDIANCUT)
    p = p.point(lambda i: i + 1)                                        # shift colours up one to free index 0
    pal = p.getpalette()[:255 * 3]; p.putpalette([0, 0, 0] + pal)
    p.paste(0, mask=alpha.point(lambda a: 255 if a < 128 else 0))
    return p


def thumb(item, size=320):
    if item["format"] == "svg": return path(item).read_bytes(), MIME["svg"]
    im = image(item); im.thumbnail((size, size), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, "WEBP", quality=85)
    return buf.getvalue(), MIME["webp"]


def jpeg_for_claude(item, size=1024):
    """A small JPEG of the image (on a checkerboard if it has transparency), for Claude to look at."""
    if item["format"] == "svg": raise MediaError("Claude can't look at SVG images here.")
    im = image(item); im.thumbnail((size, size), Image.LANCZOS)
    return _jpeg(im)


def _jpeg(im):
    if im.mode == "RGBA":
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255)); sq = 16
        for y in range(0, im.size[1], sq):
            for x in range((y // sq) % 2 * sq, im.size[0], 2 * sq): bg.paste((222, 222, 222, 255), (x, y, x + sq, y + sq))
        bg.alpha_composite(im); im = bg
    buf = io.BytesIO(); im.convert("RGB").save(buf, "JPEG", quality=85)
    return buf.getvalue()


# ---------------------------------------------------------------- edits (each makes a new item)

OPS = ("crop", "trim", "resize", "rotate", "flip", "remove_background", "convert", "pad", "talk", "bob")


def _box(b, w, h, name="box"):
    """A box given as fractions of the image [x0, y0, x1, y1] (0 to 1), in pixels."""
    try: x0, y0, x1, y1 = [float(v) for v in b]
    except (TypeError, ValueError): raise MediaError(f"The {name} needs four numbers: left, top, right, bottom (as fractions from 0 to 1).")
    x0, x1 = sorted((max(0.0, min(1.0, x0)), max(0.0, min(1.0, x1)))); y0, y1 = sorted((max(0.0, min(1.0, y0)), max(0.0, min(1.0, y1))))
    if x1 - x0 < 0.01 or y1 - y0 < 0.01: raise MediaError(f"The {name} is too small.")
    return round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h)


def edit(item_id, op, params=None, name=None):
    """Apply one edit and save the result as a new item. Returns it."""
    params = dict(params or {})
    src = get(item_id)
    if src is None: raise MediaError("That image isn't in the library.")
    if op not in OPS: raise MediaError(f"Unknown edit “{op}”. Available: {', '.join(OPS)}.")
    if op == "convert" and src.get("animated"): raise MediaError("An animation stays an animation. Download it as GIF or WebP instead.")
    fr = frames(src) if op not in ("talk", "bob") else [image(src)]
    w, h = fr[0].size
    label = {"crop": "cropped", "trim": "trimmed", "resize": "resized", "rotate": "rotated", "flip": "flipped", "remove_background": "cut out",
             "convert": params.get("format", "converted"), "pad": "padded", "talk": "talking", "bob": "moving"}[op]
    animated = src.get("animated")
    if op == "crop":
        b = _box(params.get("box"), w, h); fr = [f.crop(b) for f in fr]
    elif op == "trim":
        boxes = [f.convert("RGBA").getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox() for f in fr]
        boxes = [b for b in boxes if b]
        if not boxes: raise MediaError("The image is empty.")
        b = (min(x[0] for x in boxes), min(x[1] for x in boxes), max(x[2] for x in boxes), max(x[3] for x in boxes))
        fr = [f.crop(b) for f in fr]
    elif op == "resize":
        side = int(params.get("max", 1024))
        if not 16 <= side <= MAX_SIDE: raise MediaError(f"Choose a size from 16 to {MAX_SIDE} pixels.")
        for f in fr: f.thumbnail((side, side), Image.LANCZOS)
    elif op == "rotate":
        deg = int(params.get("degrees", 90)) % 360
        fr = [f.rotate(-deg, expand=True, resample=Image.BICUBIC) for f in fr]
    elif op == "flip":
        fr = [ImageOps.mirror(f) if params.get("direction", "horizontal") == "horizontal" else ImageOps.flip(f) for f in fr]
    elif op == "pad":
        m = float(params.get("margin", 0.06)); s = max(w, h); side = round(s * (1 + 2 * m))
        fr = [_padded(f, side) for f in fr]
    elif op == "remove_background":
        fr = [remove_background(f, params.get("box")) for f in fr]
        tb = [f.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox() for f in fr]
        if all(tb): b = (min(x[0] for x in tb), min(x[1] for x in tb), max(x[2] for x in tb), max(x[3] for x in tb)); fr = [f.crop(b) for f in fr]
    elif op == "talk":
        fr = talk_frames(fr[0], params); animated = {"frames": len(fr), "fps": int(params.get("fps", 14)), "mode": "talk"}
    elif op == "bob":
        fr = bob_frames(fr[0], params); animated = {"frames": len(fr), "fps": int(params.get("fps", 12)), "mode": "loop"}
    alpha = any(_has_alpha(f) for f in fr)
    fmt = params.get("format") if op == "convert" else None
    if animated: data, fmt = _sprite(fr), "webp"
    else:
        if fmt and fmt not in ("png", "jpg", "webp"): raise MediaError("Convert to png, jpg or webp (gif is offered when you download).")
        data, fmt = _encode(fr[0], fmt or ("png" if alpha else src["format"] if src["format"] in ("png", "jpg", "webp") else "png"))
        if fmt == "jpg": alpha = False
    w2, h2 = fr[0].size
    kind = params.get("kind") or src["kind"]
    if op == "remove_background" and kind in ("photo", "background", "other"): kind = "mascot" if src["kind"] == "mascot" else "other"
    return _store(data, fmt, w2, h2, alpha, name or f"{src['name']} ({label})", kind, src.get("description", ""), src["id"],
                  f"{op} of {src['name']}", animated)


def _padded(im, side):
    out = Image.new("RGBA", (side, side), (0, 0, 0, 0)); im = im.convert("RGBA")
    out.paste(im, ((side - im.size[0]) // 2, (side - im.size[1]) // 2), im); return out


# ---------------------------------------------------------------- background removal (Segment Anything, run on this computer)

_sam = {}


def _load_sam(status=None):
    with _lock:
        if "model" not in _sam:
            if status: status("Loading the background-removal model (the first time it downloads, about 375 MB)…")
            from transformers import SamModel, SamProcessor
            _sam["proc"] = SamProcessor.from_pretrained(SAM_MODEL); _sam["model"] = SamModel.from_pretrained(SAM_MODEL).eval()
    return _sam["proc"], _sam["model"]


def remove_background(im, box=None, status=None):
    """The subject inside `box` (fractions [x0, y0, x1, y1]; the whole picture if None) on a transparent background, with soft edges."""
    import numpy as np, torch
    rgb = im.convert("RGB"); w, h = rgb.size
    b = list(_box(box, w, h)) if box else [2, 2, w - 2, h - 2]
    proc, model = _load_sam(status)
    inp = proc(rgb, input_boxes=[[b]], return_tensors="pt")
    with torch.no_grad(): out = model(**inp, multimask_output=True)
    logits = proc.image_processor.post_process_masks(out.pred_masks, inp["original_sizes"], inp["reshaped_input_sizes"], binarize=False)[0][0]
    best = int(out.iou_scores[0, 0].argmax())
    a = torch.sigmoid(logits[best]).numpy()
    if box:                                                     # stay near the box (a glow may spill a little past it), ignore anything far away
        x0, y0, x1, y1 = b; mx, my = round((x1 - x0) * 0.2), round((y1 - y0) * 0.2)
        keep = np.zeros_like(a); keep[max(0, y0 - my):y1 + my, max(0, x0 - mx):x1 + mx] = 1; a = a * keep
    if a.max() < 0.5: raise MediaError("Couldn't find a clear subject to keep. Try drawing the box more tightly around it.")
    alpha = (np.clip(a, 0, 1) * 255).astype("uint8")
    if im.mode == "RGBA": alpha = np.minimum(alpha, np.asarray(im.getchannel("A")))
    out_im = rgb.convert("RGBA"); out_im.putalpha(Image.fromarray(alpha, "L"))
    return out_im


# ---------------------------------------------------------------- simple animations from a single picture

def talk_frames(im, p):
    """A talking mouth: the jaw below the mouth line drops a few pixels and springs back, with the mouth dark behind it.

    p["mouth"]: [x0, y0, x1, y1] fractions: the mouth's corners (x0..x1), the mouth line (y0) and the bottom of the chin (y1).
    p["line"]: optional [[x, y], ...] fractions for a mouth line that slants or curves (instead of the straight one at y0).
    p["open"]: how far it opens, as a fraction of the image height (default 0.018)."""
    import numpy as np
    a = np.asarray(im.convert("RGBA")).astype(np.float32); H, W = a.shape[:2]
    x0, y0, x1, y1 = _box(p.get("mouth"), W, H, "mouth box")
    pts = p.get("line") or [[x0 / W, y0 / H], [x1 / W, y0 / H]]
    try: xs = np.array([float(q[0]) * W for q in pts]); ys = np.array([float(q[1]) * H for q in pts])
    except (TypeError, ValueError, IndexError): raise MediaError("The mouth line needs points like [[x, y], [x, y]].")
    order = np.argsort(xs); xs, ys = xs[order], ys[order]
    X, Y = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))
    yl = np.interp(X, xs, ys)
    cx, half = (xs[0] + xs[-1]) / 2, (xs[-1] - xs[0]) / 2 + 2
    wx = np.clip(1 - ((X - cx) / half) ** 2, 0, 1) ** 2                       # widest in the middle, closed at both corners
    wy = np.clip((y1 - Y) / np.maximum(y1 - yl, 1), 0, 1) * (Y >= yl - 1)     # the jaw moves; the chin's bottom edge stays
    open_px = float(p.get("open", 0.018)) * H
    mouth = np.array([38, 18, 24, 255], np.float32)
    cols = X.astype(int); out_frames = []
    for s in (0, .4, .75, 1, .7, .35):
        d = s * open_px * wx * wy; sy = Y - d
        r0 = np.clip(np.floor(sy).astype(int), 0, H - 1); r1 = np.clip(r0 + 1, 0, H - 1); f = (sy - np.floor(sy))[..., None]
        out = a[r0, cols] * (1 - f) + a[r1, cols] * f
        gap = ((sy < yl) & (d > 0.3))[..., None]
        k = np.clip((yl - sy) / 1.5, 0, 1)[..., None] * gap
        out = out * (1 - k) + mouth * k
        out_frames.append(Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA"))
    return out_frames + out_frames[::-1][1:-1]                               # open and close


def bob_frames(im, p):
    """A gentle up-and-down float (for a character that should feel alive while it isn't talking)."""
    import math
    im = im.convert("RGBA"); w, h = im.size; amp = max(2, round(float(p.get("amount", 0.02)) * h)); n = 16
    out = []
    for k in range(n):
        f = Image.new("RGBA", (w, h + amp), (0, 0, 0, 0)); f.paste(im, (0, round(amp / 2 * (1 - math.cos(2 * math.pi * k / n)))), im); out.append(f)
    return out


# ---------------------------------------------------------------- pages: <img data-asset="id"> becomes the image

ASSET_TAG = re.compile(r"<img\b([^>]*?)\bdata-asset\s*=\s*[\"']([^\"']+)[\"']([^>]*)>", re.I)
SPRITE_CSS = """/*h2m:media*/
.h2m-sprite{display:inline-block;background-repeat:no-repeat;background-position:0 0;max-width:100%}
.h2m-sprite.h2m-loop{animation-name:h2m-sprite;animation-iteration-count:infinite}
#stage.speaking .slide.active .h2m-sprite.h2m-talk{animation-name:h2m-sprite;animation-iteration-count:infinite}
@keyframes h2m-sprite{to{background-position:100% 0}}
/*h2m:end*/"""


def asset_ids(html): return [m.group(2) for m in ASSET_TAG.finditer(html or "")]


def resolve(html, lookup=None):
    """Replace every <img data-asset="..."> with the image itself. Returns (html, missing ids)."""
    lookup = lookup or get
    missing, cache = [], {}

    def one(m):
        attrs = m.group(1) + " " + m.group(3)
        iid = m.group(2); it = cache.get(iid) or lookup(iid)
        if it is None: missing.append(iid); return m.group(0)
        cache[iid] = it
        alt = re.search(r'\balt\s*=\s*"([^"]*)"', attrs); alt = alt.group(1) if alt else _html.escape(it["name"], quote=True)
        attrs = re.sub(r'\s(?:src|alt)\s*=\s*("[^"]*"|\'[^\']*\'|\S+)', "", attrs).strip().rstrip("/").strip()
        if not it.get("animated"):
            return f'<img {attrs} src="{data_uri(it)}" alt="{alt}" data-asset="{iid}" draggable="false">'.replace("  ", " ")
        an = it["animated"]; n = an["frames"]
        cls = re.search(r'\bclass\s*=\s*"([^"]*)"', attrs); style = re.search(r'\bstyle\s*=\s*"([^"]*)"', attrs)
        rest = re.sub(r'\s(?:class|style)\s*=\s*"[^"]*"', "", " " + attrs).strip()
        mode = "h2m-talk" if an.get("mode") == "talk" else "h2m-loop"
        css = (f"aspect-ratio:{it['w']}/{it['h']};background-image:url({data_uri(it)});background-size:{n * 100}% 100%;"
               f"animation-duration:{n / an['fps']:.3f}s;animation-timing-function:steps({n},jump-none);" + (style.group(1) if style else ""))
        klass = f"h2m-sprite {mode}" + (f" {cls.group(1)}" if cls else "")
        return f'<span role="img" aria-label="{alt}" data-asset="{iid}" class="{klass}" style="{css}"{(" " + rest) if rest else ""}></span>'

    return ASSET_TAG.sub(one, html or ""), missing


def catalog_text(items=None, limit=40):
    """The library as the slide designer and the assistant see it."""
    items = listing() if items is None else items
    if not items: return ""
    rows = []
    for i in items[:limit]:
        bits = [i["kind"], f"{i['w']}×{i['h']}", "transparent background" if i["transparent"] else "opaque",
                {"talk": "animated: talks while the narrator speaks", "loop": "animated: loops"}.get((i.get("animated") or {}).get("mode"), "")]
        rows.append(f"- {i['id']}: “{i['name']}” ({', '.join(b for b in bits if b)})" + (f". {i['description']}" if i.get("description") else ""))
    return "\n".join(rows)


# ---------------------------------------------------------------- Claude looks at an image (describing it, finding a part of it)

LOOK_SYSTEM = """You look at images for a studio that makes narrated training videos, and you are precise about where things are.
Coordinates are fractions of the image's width and height, from 0 to 1, measured from the top-left corner. A light checkerboard
in the picture means that area is transparent."""

DESCRIBE_SCHEMA = {"type": "object", "properties": {
    "name": {"type": "string"}, "kind": {"type": "string", "enum": list(KINDS)}, "description": {"type": "string"},
    "subject": {"type": "array", "items": {"type": "number"}}},
    "required": ["name", "kind", "description", "subject"], "additionalProperties": False}

LOCATE_SCHEMA = {"type": "object", "properties": {
    "found": {"type": "boolean"}, "box": {"type": "array", "items": {"type": "number"}},
    "line": {"type": ["array", "null"], "items": {"type": "array", "items": {"type": "number"}}}, "note": {"type": "string"}},
    "required": ["found", "box", "line", "note"], "additionalProperties": False}

WHAT = {
    "subject": "the main subject (the person, character, object or logo the picture is about), including anything it holds or touches. "
               "box = its tight bounding box [left, top, right, bottom]. line = null.",
    "mouth": "the character's mouth, for a talking animation. box = [left, top, right, bottom] where left and right are the mouth's two "
             "corners, top is the line where the upper and lower lips (or jaws) meet, and bottom is the bottom of the chin or lower jaw "
             "(everything between top and bottom moves when it talks). line = 3 to 6 points [x, y] along where the lips meet, from the "
             "left corner to the right corner, following its curve.",
}


def _look(item, text, schema, call=None, crop=None):
    """Ask Claude about the image (or the `crop` [x0, y0, x1, y1] fractions of it, enlarged). Coordinates in the answer are of what it saw."""
    from html2mp4 import ai
    call = call or ai.structured
    if crop:
        im = image(item); w, h = im.size; c = _box(crop, w, h, "area")
        part = im.crop(c); scale = 900 / max(part.size); part = part.resize((max(1, round(part.size[0] * scale)), max(1, round(part.size[1] * scale))), Image.LANCZOS)
        tmp = {"format": "png", "transparent": part.mode == "RGBA", "animated": None}
        jpg = _jpeg(part)
    else: jpg = jpeg_for_claude(item)
    block = {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(jpg).decode()}}
    answer, usage = call(LOOK_SYSTEM, [block, {"type": "text", "text": text}], schema, effort="low", max_tokens=4000)
    return answer, ai.cost(usage)


def describe(item_id, call=None):
    """Claude names and describes the image, says what kind it is and where its subject is. Saves the description (and the subject box)."""
    it = get(item_id)
    if it is None: raise MediaError("That image isn't in the library.")
    a, cost = _look(it, f"This image is {it['w']}×{it['h']} pixels, uploaded as “{it['name']}”. Give it a short name (2 to 4 words), "
                        "the kind it is, a one or two sentence description a slide designer can use (what it shows, its style and colours, "
                        "which way a character faces, whether the background is transparent), and `subject`: " + WHAT["subject"], DESCRIBE_SCHEMA, call)
    with _lock:
        items = listing(); cur = next(i for i in items if i["id"] == item_id)
        if not cur.get("description"): cur["description"] = a["description"].strip()[:400]
        if len(a.get("subject") or []) == 4: cur["subject"] = [round(float(v), 4) for v in a["subject"]]
        cur["suggested"] = {"name": a["name"].strip()[:60], "kind": a["kind"]}
        _save(items)
        return cur, cost


def locate(item_id, what, call=None):
    """Where a part of the image is ("subject" or "mouth"), as {box, line} in fractions of the whole image. Claude looks twice: once
    at the whole picture, then closer at the area it found, which makes the result precise enough to animate. Raises MediaError if
    it can't be found."""
    it = get(item_id)
    if it is None: raise MediaError("That image isn't in the library.")
    ask = lambda shape: (f"This picture is {shape}. Find {WHAT.get(what, what)} If it isn't there, set found to false and say why in note.")
    a, cost = _look(it, ask(f"{it['w']}×{it['h']} pixels"), LOCATE_SCHEMA, call)
    if not a.get("found") or len(a.get("box") or []) != 4: raise MediaError(f"Claude couldn't find the {what} in “{it['name']}”: {a.get('note') or 'not clear enough'}.")
    x0, y0, x1, y1 = [float(v) for v in a["box"]]
    pad_x, pad_y = max(0.04, (x1 - x0) * 0.6), max(0.04, (y1 - y0) * 0.6)
    area = [max(0.0, x0 - pad_x), max(0.0, y0 - pad_y), min(1.0, x1 + pad_x), min(1.0, y1 + pad_y)]
    b, c2 = _look(it, ask("a close-up of part of a larger image") + " Give coordinates as fractions of this close-up.", LOCATE_SCHEMA, call, crop=area)
    cost += c2
    if b.get("found") and len(b.get("box") or []) == 4:                  # map the close-up's answer back onto the whole image
        ax, ay, aw, ah = area[0], area[1], area[2] - area[0], area[3] - area[1]
        a = {"box": [ax + b["box"][0] * aw, ay + b["box"][1] * ah, ax + b["box"][2] * aw, ay + b["box"][3] * ah],
             "line": [[ax + x * aw, ay + y * ah] for x, y in b["line"]] if b.get("line") else a.get("line")}
    return {"box": [round(v, 4) for v in a["box"]], "line": [[round(x, 4), round(y, 4)] for x, y in a["line"]] if a.get("line") else None}, cost


def smart_edit(item_id, op, params=None, name=None, call=None, status=None):
    """An edit where Claude fills in what a person wouldn't want to measure: where the subject is (to remove the background) or where
    the mouth is (to make a character talk). Returns (new item, Claude cost)."""
    params, cost = dict(params or {}), 0.0
    it = get(item_id)
    if it is None: raise MediaError("That image isn't in the library.")
    if op == "remove_background" and not params.get("box"):
        if it.get("subject"): params["box"] = it["subject"]
        else:
            if status: status("Finding the subject…")
            try: found, cost = locate(item_id, "subject", call); params["box"] = found["box"]
            except Exception: params["box"] = None                       # no key, or not found: keep the main thing in the whole picture
    if op == "talk" and not params.get("mouth"):
        if status: status("Finding the mouth…")
        found, c = locate(item_id, "mouth", call); cost += c
        params["mouth"], params["line"] = found["box"], found.get("line")
    if status: status({"remove_background": "Removing the background…", "talk": "Making it talk…"}.get(op, "Editing…"))
    return edit(item_id, op, params, name), cost
