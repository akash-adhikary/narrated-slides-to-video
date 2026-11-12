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


def update(item_id, name=None, kind=None, description=None, speaker=None, voice=None):
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
        if voice is not None:                        # the voice this character speaks with ("" = the default character voice)
            voice = re.sub(r"\s+", " ", str(voice)).strip()[:60]
            if voice:
                from html2mp4 import script
                try: script.voice_id(voice)
                except script.ScriptError as e: raise MediaError(str(e).split(": ", 1)[-1])
                it["voice"] = voice
            else: it.pop("voice", None)
        if speaker is not None:                      # the script's speaker this character speaks as ("" = the narrator)
            speaker = re.sub(r"\s+", " ", str(speaker)).strip()[:30]
            if speaker: it["speaker"] = speaker
            else: it.pop("speaker", None)
        _save(items); return it


def delete(item_id):
    with _lock:
        items = listing(); it = next((i for i in items if i["id"] == item_id), None)
        if it is None: return
        try: path(it).unlink()
        except FileNotFoundError: pass
        for old in (MEDIA / ".previews").glob(f"{item_id}-*"): old.unlink(missing_ok=True)
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
    """Add an uploaded file (an image, or a video clip). Returns the new item."""
    if is_video(raw, filename): return add_video(raw, filename, name, kind, description)
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


def _store(data, fmt, w, h, alpha, name, kind, description, parent, note, animated=None, extra=None):
    with _lock:
        items = listing()
        name = _unique_name(name, items)
        iid = _unique_id(name, items)
        MEDIA.mkdir(parents=True, exist_ok=True)
        (MEDIA / f"{iid}.{fmt}").write_bytes(data)
        it = {"id": iid, "name": name, "kind": kind if kind in KINDS else _guess_kind(w, h, alpha), "description": description or "",
              "file": f"{iid}.{fmt}", "format": fmt, "w": w, "h": h, "transparent": bool(alpha), "bytes": len(data),
              "animated": animated, "created": time.time(), "parent": parent, "note": note, **(extra or {})}
        items.append(it); _save(items)
        return it


def _guess_kind(w, h, alpha):
    if alpha: return "icon" if max(w, h) <= 256 else "other"
    return "photo"


# ---------------------------------------------------------------- reading images back

def image(item, frame=0, row=0):
    """The item as a Pillow image (an animation's frame `frame`, of row `row`: a character's idle loop is row 0, talking row 1)."""
    if item["format"] == "svg": raise MediaError("SVG images can't be edited here. Convert it to PNG first (open it and export it as PNG).")
    if item["format"] in VIDEO_FORMATS: return video_frame(item, item.get("poster", 0.0))     # a clip's picture is its poster frame
    im = Image.open(path(item)); im.load()
    if item.get("animated"):
        w, h = item["w"], item["h"]; row = min(row, item["animated"].get("rows", 1) - 1)
        im = im.crop((frame * w, row * h, frame * w + w, row * h + h))
    return im.convert("RGBA") if item["transparent"] else im.convert("RGB")


def frames(item, row=0):
    if not item.get("animated"): return [image(item)]
    an = item["animated"]; w, h = item["w"], item["h"]; row = min(row, an.get("rows", 1) - 1)
    sheet = Image.open(path(item)); sheet.load()                                  # the sheet is decoded once, however many frames it holds
    sheet = sheet.convert("RGBA" if item["transparent"] else "RGB")
    return [sheet.crop((k * w, row * h, k * w + w, row * h + h)) for k in range(an["frames"])]


def preview(item, size=360):
    """What the Studio shows for an item: a small still, or for an animation a small looping animated WebP (cached, since making it takes a moment).
    Returns (bytes, mime)."""
    cache = MEDIA / ".previews"; cache.mkdir(parents=True, exist_ok=True)
    f = cache / f"{item['id']}-{int(path(item).stat().st_mtime)}-{size}.webp"
    if f.exists(): return f.read_bytes(), MIME["webp"]
    if item.get("animated"):
        fr = frames(item, 0); sc = min(1.0, size / max(fr[0].size))
        fr = [x.resize((max(1, round(x.width * sc)), max(1, round(x.height * sc))), Image.LANCZOS) for x in fr]
        buf = io.BytesIO(); fr[0].save(buf, "WEBP", save_all=True, append_images=fr[1:], duration=round(1000 / item["animated"]["fps"]), loop=0, quality=70, method=1)
        data = buf.getvalue()
    else: data = thumb(item, size)[0]
    for old in cache.glob(f"{item['id']}-*"): old.unlink(missing_ok=True)
    f.write_bytes(data); return data, MIME["webp"]


MIME = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp", "svg": "image/svg+xml", "gif": "image/gif", "webm": "video/webm"}


def data_uri(item):
    return f"data:{MIME[item['format']]};base64," + base64.b64encode(path(item).read_bytes()).decode()


def export(item, fmt, row=0):
    """The image as a file to download, in png, jpg, webp or gif (an animation becomes an animated gif or webp; `row` 1 is a
    character's talking loop)."""
    fmt = {"jpeg": "jpg"}.get(fmt, fmt)
    if item["format"] in VIDEO_FORMATS:
        if fmt == "webm": return path(item).read_bytes(), MIME["webm"]
        if fmt in ("png", "jpg", "webp"): fr = [image(item)]                # its poster frame
        else: raise MediaError("A video clip downloads as WebM, or its first picture as PNG, JPG or WebP.")
        buf = io.BytesIO(); fr[0].convert("RGB" if fmt == "jpg" else "RGBA").save(buf, {"jpg": "JPEG"}.get(fmt, fmt.upper())); return buf.getvalue(), MIME[fmt]
    if fmt not in ("png", "jpg", "webp", "gif"): raise MediaError("Choose png, jpg, webp or gif.")
    if item["format"] == "svg":
        if fmt != "png": raise MediaError("An SVG can be downloaded as it is, or as PNG.")
        raise MediaError("Converting SVG to PNG isn't available yet. Download the SVG itself.")
    fr = frames(item, row); buf = io.BytesIO()
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

OPS = ("crop", "trim", "resize", "rotate", "flip", "remove_background", "convert", "pad", "talk", "bob", "animate", "character", "clip")
VIDEO_OPS = ("remove_background", "character", "clip")                    # the edits a video clip can have


def _box(b, w, h, name="box"):
    """A box given as fractions of the image [x0, y0, x1, y1] (0 to 1), in pixels."""
    try: x0, y0, x1, y1 = [float(v) for v in b]
    except (TypeError, ValueError): raise MediaError(f"The {name} needs four numbers: left, top, right, bottom (as fractions from 0 to 1).")
    x0, x1 = sorted((max(0.0, min(1.0, x0)), max(0.0, min(1.0, x1)))); y0, y1 = sorted((max(0.0, min(1.0, y0)), max(0.0, min(1.0, y1))))
    if x1 - x0 < 0.01 or y1 - y0 < 0.01: raise MediaError(f"The {name} is too small.")
    return round(x0 * w), round(y0 * h), round(x1 * w), round(y1 * h)


def edit(item_id, op, params=None, name=None, status=None):
    """Apply one edit and save the result as a new item. Returns it."""
    params = dict(params or {})
    src = get(item_id)
    if src is None: raise MediaError("That image isn't in the library.")
    if op not in OPS: raise MediaError(f"Unknown edit “{op}”. Available: {', '.join(OPS)}.")
    if src["format"] in VIDEO_FORMATS:
        if op == "remove_background": return video_cutout(src, params, name, status)
        if op == "character": return video_character(src, params, name, status)
        if op == "clip": return video_part(src, params, name)
        raise MediaError(f"A video clip can have these edits: remove the background, or make a talking character from it.")
    if op == "character": raise MediaError("A talking character is made from a video clip of the character speaking. Upload the clip first.")
    if op == "convert" and src.get("animated"): raise MediaError("An animation stays an animation. Download it as GIF or WebP instead.")
    if op in ("talk", "bob", "animate") and src.get("animated"): raise MediaError("This image is already animated. Start from the still picture.")
    fr = frames(src) if op not in ("talk", "bob", "animate") else [image(src)]
    w, h = fr[0].size
    label = {"crop": "cropped", "trim": "trimmed", "resize": "resized", "rotate": "rotated", "flip": "flipped", "remove_background": "cut out",
             "convert": params.get("format", "converted"), "pad": "padded", "talk": "talking", "bob": "moving", "animate": "animated"}[op]
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
    elif op == "animate":
        if not src["transparent"]: raise MediaError("Bring to life works on a cut-out. Remove the background first.")
        idle, talking = character_frames(fr[0], params.get("parts") or [], params.get("mouth"))
        data, fw, fh = _sprite_rows([idle, talking] if talking else [idle])
        animated = {"frames": len(idle), "fps": 16, "mode": "character" if talking else "loop", "rows": 2 if talking else 1}
        return _store(data, "webp", fw, fh, True, name or f"{src['name']} (animated)", params.get("kind") or src["kind"],
                      src.get("description", ""), src["id"], f"animate of {src['name']}", animated)
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


def subject_box(im):
    """Where the subject is, as fractions [x0, y0, x1, y1], when that is clear without asking anyone: the opaque part of a
    picture with transparency, or whatever stands out from a plain backdrop (the colour along the edges). None if unclear."""
    import numpy as np
    if im.mode == "RGBA" and _has_alpha(im):
        bb = im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
        return [bb[0] / im.width, bb[1] / im.height, bb[2] / im.width, bb[3] / im.height] if bb else None
    a = np.asarray(im.convert("RGB")).astype(np.int16); h, w = a.shape[:2]
    rim = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bg = np.median(rim, axis=0)
    if (np.abs(rim - bg).sum(1) < 40).mean() < 0.6: return None        # a busy backdrop (a photo): no plain colour to stand out from
    ys, xs = np.where(np.abs(a - bg).sum(2) > 60)
    if len(xs) < 0.01 * w * h: return None
    x0, x1, y0, y1 = np.percentile(xs, 0.2), np.percentile(xs, 99.8), np.percentile(ys, 0.2), np.percentile(ys, 99.8)
    mx, my = 0.02 * w, 0.02 * h
    return [float(max(0, x0 - mx) / w), float(max(0, y0 - my) / h), float(min(w, x1 + mx) / w), float(min(h, y1 + my) / h)]


def remove_background(im, box=None, status=None):
    """The subject inside `box` (fractions [x0, y0, x1, y1]; the whole picture if None) on a transparent background, with soft edges."""
    import numpy as np, torch
    rgb = im.convert("RGB"); w, h = rgb.size
    if not box: box = subject_box(im)                          # no box: find the subject first (a whole-picture box selects the backdrop)
    b = list(_box(box, w, h)) if box else [2, 2, w - 2, h - 2]
    proc, model = _load_sam(status)
    inp = proc(rgb, input_boxes=[[b]], return_tensors="pt")
    with torch.no_grad(): out = model(**inp, multimask_output=True)
    logits = proc.image_processor.post_process_masks(out.pred_masks, inp["original_sizes"], inp["reshaped_input_sizes"], binarize=False)[0][0]
    masks = [torch.sigmoid(logits[k]).numpy() for k in range(logits.shape[0])]
    # the subject doesn't cover the backdrop along the picture's edges; a mask that does is the background, so it is never the one
    # kept (only the edge pixels that look like backdrop count: a subject may well touch the edge, cut off by the frame)
    px = np.asarray(rgb).astype(np.int16); rim = np.concatenate([px[0], px[-1], px[:, 0], px[:, -1]])
    plain = np.abs(rim - np.median(rim, axis=0)).sum(1) < 40
    if plain.mean() < 0.3: plain = np.ones_like(plain)
    edge = lambda m: float(np.concatenate([m[0], m[-1], m[:, 0], m[:, -1]])[plain].mean())
    order = sorted(range(len(masks)), key=lambda k: -float(out.iou_scores[0, 0, k]))
    best = next((k for k in order if edge(masks[k]) < 0.5), None)
    a = masks[best] if best is not None else 1 - masks[order[0]]
    if box:                                                     # stay near the box (a glow may spill a little past it), ignore anything far away
        x0, y0, x1, y1 = b; mx, my = round((x1 - x0) * 0.2), round((y1 - y0) * 0.2)
        keep = np.zeros_like(a); keep[max(0, y0 - my):y1 + my, max(0, x0 - mx):x1 + mx] = 1; a = a * keep
    if a.max() < 0.5: raise MediaError("Couldn't find a clear subject to keep. Try drawing the box more tightly around it.")
    alpha = (np.clip(a, 0, 1) * 255).astype("uint8")
    if im.mode == "RGBA": alpha = np.minimum(alpha, np.asarray(im.getchannel("A")))
    out_im = rgb.convert("RGBA"); out_im.putalpha(Image.fromarray(alpha, "L"))
    clean = _defringe(np.asarray(out_im).astype(np.float32) / 255.0)          # edges take the subject's colour, not the old background's
    return Image.fromarray((clean * 255).clip(0, 255).astype("uint8"), "RGBA")


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
.h2m-sprite{display:inline-block;background-repeat:no-repeat;background-position:0 0;max-width:100%;width:100%}
.h2m-sprite.h2m-loop{animation-name:h2m-sprite;animation-iteration-count:infinite}
#stage.speaking:not([data-speaker]) .slide.active .h2m-sprite.h2m-talk:not([data-speaker]){animation-name:h2m-sprite;animation-iteration-count:infinite}
.h2m-sprite.h2m-char{animation-name:h2m-sprite-x;animation-iteration-count:infinite;background-position-y:0;position:relative}
.h2m-sprite.h2m-char::after{content:"";position:absolute;inset:0;background-image:inherit;background-size:inherit;background-repeat:no-repeat;
  background-position:0 100%;animation:inherit;animation-name:h2m-sprite-x;opacity:0;transition:opacity .16s ease}
#stage.speaking:not([data-speaker]) .slide.active .h2m-sprite.h2m-char:not([data-speaker])::after{opacity:1}
@keyframes h2m-sprite{to{background-position:100% 0}}
@keyframes h2m-sprite-x{to{background-position-x:100%}}
.h2m-actor{display:inline-block;position:relative;max-width:100%;width:100%}
.h2m-actor>.h2m-sprite{display:block;width:100%;transform-origin:50% 100%;transition:opacity .14s linear}
.h2m-sprite{transform-origin:50% 100%}
.h2m-act{position:absolute;inset:0;width:100%;height:100%;object-fit:contain;opacity:0;transition:opacity .14s linear;pointer-events:none}
.h2m-act.on{opacity:1}
.h2m-actor.acting>.h2m-sprite{opacity:0;transition:opacity 0s linear .14s}
/*h2m:end*/"""


def _attr(attrs, name):
    """An attribute's value, written with double quotes, single quotes or none."""
    m = re.search(rf'(?:^|\s){name}\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))', attrs, re.I)
    return None if not m else next(g for g in m.groups() if g is not None)


def speaker_css(names):
    """A character that speaks as someone (data-speaker="Spotter") talks only while that speaker does; an unnamed one talks with the
    narrator. One rule per speaker, since CSS can't match two attributes against each other."""
    out = []
    for n in names or ():
        q = json.dumps(str(n))
        out.append(f"#stage.speaking[data-speaker={q}] .slide.active .h2m-sprite.h2m-char[data-speaker={q}]::after{{opacity:1}}\n"
                   f"#stage.speaking[data-speaker={q}] .slide.active .h2m-sprite.h2m-talk[data-speaker={q}]{{animation-name:h2m-sprite;animation-iteration-count:infinite}}")
    return "\n".join(out)


def asset_ids(html): return [m.group(2) for m in ASSET_TAG.finditer(html or "")]


def resolve(html, lookup=None, clips=None, defs=None):
    """Replace every <img data-asset="..."> with the image itself. Returns (html, missing ids).
    `clips` ({character name: {action, ...}}): the actions of a character that a module uses as video clips, which go into the page
    inside the character's picture, ready for the player to show (and the video renderer to step through).
    `defs` (a dict): when given, an animated picture's data goes there once (to be written as the class `h2m-pic-<id>`) instead of into every place it is used."""
    lookup = lookup or get
    missing, cache = [], {}

    def one(m):
        attrs = m.group(1) + " " + m.group(3)
        iid = m.group(2); it = cache.get(iid) or lookup(iid)
        if it is None: missing.append(iid); return m.group(0)
        cache[iid] = it
        alt = _attr(attrs, "alt"); alt = _html.escape(_html.unescape(alt), quote=True) if alt is not None else _html.escape(it["name"], quote=True)
        attrs = re.sub(r'\s(?:src|alt)\s*=\s*("[^"]*"|\'[^\']*\'|\S+)', "", attrs).strip().rstrip("/").strip()
        if it.get("speaker") and "data-speaker" not in attrs: attrs += f' data-speaker="{_html.escape(it["speaker"], quote=True)}"'   # who it speaks as
        if it["format"] in VIDEO_FORMATS:                 # a clip: silent, and played in step with the slide (the player and the renderer drive it)
            return (f'<video {attrs} src="{data_uri(it)}" aria-label="{alt}" data-asset="{iid}" data-h2m-video muted playsinline '
                    f'preload="auto" disablepictureinpicture></video>').replace("  ", " ")
        if not it.get("animated"):
            return f'<img {attrs} src="{data_uri(it)}" alt="{alt}" data-asset="{iid}" draggable="false">'.replace("  ", " ")
        an = it["animated"]; n = an["frames"]
        def picture():                       # (a custom property can't hold this: browsers drop values over about 2 MB, so a class carries it)
            if defs is None: return f"background-image:url({data_uri(it)});"
            defs[iid] = data_uri(it); return ""
        pic_class = f"h2m-pic-{iid}" if defs is not None else ""
        cls, style = _attr(attrs, "class"), _attr(attrs, "style")          # either quote style (a second class="" would be ignored by the browser)
        rest = re.sub(r'\s(?:class|style)\s*=\s*(?:"[^"]*"|\'[^\']*\'|[^\s>]+)', "", " " + attrs).strip()
        mode = {"talk": "h2m-talk", "character": "h2m-char"}.get(an.get("mode"), "h2m-loop")
        css = (f"aspect-ratio:{it['w']}/{it['h']};{picture()}background-size:{n * 100}% {an.get('rows', 1) * 100}%;"
               f"animation-duration:{n / an['fps']:.3f}s;animation-timing-function:steps({n},jump-none);" + (style or ""))
        who = it.get("speaker"); used = sorted((clips or {}).get(who, ())) if who else []
        if who and clips is not None and who in clips and an.get("mode") == "character":
            # (a character that acts is always wrapped, even when its actions are only motions: the slide's own reveal rules put a transform and a
            # transition on anything with data-c, which would swallow a jump, so the designer's attributes go on the box and the motion on the picture)
            # a character with action clips: an outer box carries the designer's class, size and position; the picture and the clips sit inside
            inner_css = f"aspect-ratio:{it['w']}/{it['h']};{picture()}background-size:{n * 100}% {an.get('rows', 1) * 100}%;" \
                        f"animation-duration:{n / an['fps']:.3f}s;animation-timing-function:steps({n},jump-none);"
            vids = "".join(f'<video class="h2m-act" data-act="{_html.escape(k, quote=True)}" src="{data_uri(get(it["actions"][k]))}" muted playsinline preload="auto" '
                           f'disablepictureinpicture></video>' for k in used)
            outer = f"aspect-ratio:{it['w']}/{it['h']};" + (style or "")
            return (f'<span role="img" aria-label="{alt}" data-asset="{iid}" class="h2m-actor{(" " + cls) if cls else ""}" style="{outer}"{(" " + rest) if rest else ""}>'
                    f'<span class="h2m-sprite {mode}{(" " + pic_class) if pic_class else ""}" data-speaker="{_html.escape(who, quote=True)}" style="{inner_css}"></span>{vids}</span>')
        klass = f"h2m-sprite {mode}" + (f" {pic_class}" if pic_class else "") + (f" {cls}" if cls else "")
        return f'<span role="img" aria-label="{alt}" data-asset="{iid}" class="{klass}" style="{css}"{(" " + rest) if rest else ""}></span>'

    return ASSET_TAG.sub(one, html or ""), missing


def catalog_text(items=None, limit=40):
    """The library as the slide designer and the assistant see it."""
    items = listing() if items is None else items
    if not items: return ""
    rows = []
    for i in items[:limit]:
        bits = [i["kind"], f"{i['w']}×{i['h']}", "transparent background" if i["transparent"] else "opaque",
                {"talk": "animated: talks while the narrator speaks", "loop": "animated: loops",
                 "character": "animated character: always moving, and talks while the narrator speaks"}.get((i.get("animated") or {}).get("mode"), "")]
        if i.get("speaker") and i.get("animated"):
            have = ", ".join(actions_of(i)) if (i["animated"] or {}).get("mode") == "character" else ""
            bits[-1] = bits[-1].replace("the narrator speaks", f"{i['speaker']} speaks") + (f"; a talking character that speaks as {i['speaker']}, who can: {have}" if have else "")
        if i.get("format") in VIDEO_FORMATS: bits = [i["kind"], f"{i['w']}×{i['h']}", f"video clip, {i.get('seconds', 0):g} s, plays silently from the start of its slide"]
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
    if it["format"] in VIDEO_FORMATS: return edit(item_id, op, params, name, status), 0.0      # a clip's subject is found in every frame
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
    if op == "animate" and params.get("parts") is None:
        if status: status("Finding the parts that can move…")
        params["parts"], c = find_parts(item_id, call); cost += c
        if not params["parts"]: raise MediaError(f"Claude didn't find parts that could move in “{it['name']}”. Bring to life works on a character such as a mascot.")
        if params.get("mouth") is None:
            if status: status("Finding the mouth…")
            try: found, c = locate(item_id, "mouth", call); cost += c; params["mouth"] = found
            except MediaError: params["mouth"] = None                     # no mouth: it moves, but doesn't talk
    if status: status({"remove_background": "Removing the background…", "talk": "Making it talk…", "animate": "Animating each part…"}.get(op, "Editing…"))
    return edit(item_id, op, params, name), cost


# ---------------------------------------------------------------- bringing a character to life (cut-out animation)
# Claude finds the parts that can move (tail, ears, tongue...) and where each joins the body; Segment Anything cuts each part out;
# then each part bends from its joint (nothing moves at the joint, the tip moves most), so there are no seams. The result has two
# rows of frames: the idle loop (always playing) and the same loop with the mouth talking, which a slide shows only while the
# narrator speaks.

PARTS_SCHEMA = {"type": "object", "properties": {"parts": {"type": "array", "items": {"type": "object", "properties": {
    "name": {"type": "string"}, "kind": {"type": "string", "enum": ["tail", "ear", "tongue", "wing", "arm", "other"]},
    "box": {"type": "array", "items": {"type": "number"}}, "joint": {"type": "array", "items": {"type": "number"}},
    "tip": {"type": "array", "items": {"type": "number"}}},
    "required": ["name", "kind", "box", "joint", "tip"], "additionalProperties": False}}}, "required": ["parts"], "additionalProperties": False}

# swing (degrees), cycles per loop, stretch: a happy wag, floppy ears on their own rhythm, a panting tongue
MOTION = {"tail": (18, 2, 0.0), "ear": (7, 1, 0.0), "tongue": (7, 3, 0.06), "wing": (12, 2, 0.0), "arm": (6, 1, 0.0), "other": (5, 1, 0.0)}
SPRITE_MAX_W = 16000                                                     # WebP images can't be wider than 16383 pixels


def find_parts(item_id, call=None):
    it = get(item_id)
    a, cost = _look(it, f"This picture is {it['w']}×{it['h']} pixels. List the parts of this character that could move on their own in a "
                        "simple, playful animation: a tail, each ear (separately), a tongue that sticks out, wings. For each: box = its tight "
                        "bounding box, joint = the point where it attaches to the body (it pivots there), tip = its far end. Leave out parts "
                        "that are hidden or fused to the body. If it isn't a character, return no parts.", PARTS_SCHEMA, call)
    parts = [p for p in a.get("parts", []) if len(p.get("box") or []) == 4 and len(p.get("joint") or []) == 2 and len(p.get("tip") or []) == 2][:8]
    return parts, cost


def _defringe(rgba):
    """A cut-out's soft edge still carries the colour of the background it was cut from (a dark halo on a light slide). Give edge
    pixels the colour just inside them instead. `rgba` is a float array 0..1 (straight alpha); returns a new one."""
    import numpy as np
    from scipy.ndimage import gaussian_filter
    A = rgba.copy(); solid = (A[..., 3] > 0.92).astype(np.float32)
    for r in (2, 5, 12):
        den = gaussian_filter(solid, r)[..., None]
        est = np.dstack([gaussian_filter(A[..., c] * solid, r) for c in range(3)]) / np.maximum(den, 1e-4)
        edge = (A[..., 3] <= 0.92) & (den[..., 0] > 0.02) & (solid == 0)
        A[..., :3] = np.where(edge[..., None], est, A[..., :3]); solid = np.maximum(solid, edge.astype(np.float32))
    return A


def _part_masks(rgb, alpha, parts, W, H):
    """One clean mask per part, from Segment Anything (the image's embedding is computed once and shared)."""
    import numpy as np, torch
    from scipy.ndimage import gaussian_filter, label, maximum_filter
    proc, model = _load_sam()
    with torch.no_grad(): emb = model.get_image_embeddings(proc(rgb, return_tensors="pt")["pixel_values"])
    cx, cy = W / 2, H / 2
    masks = []
    for p in parts:
        b = [p["box"][0] * W, p["box"][1] * H, p["box"][2] * W, p["box"][3] * H]
        jx, jy, tx, ty = p["joint"][0] * W, p["joint"][1] * H, p["tip"][0] * W, p["tip"][1] * H
        pos = [[(jx + 2 * tx) / 3, (jy + 2 * ty) / 3], [(jx + tx) / 2, (jy + ty) / 2]]
        inp = proc(rgb, input_boxes=[[b]], input_points=[[pos]], input_labels=[[[1, 1]]], return_tensors="pt")
        with torch.no_grad():
            out = model(image_embeddings=emb, input_boxes=inp["input_boxes"], input_points=inp["input_points"], input_labels=inp["input_labels"], multimask_output=True)
        lg = proc.image_processor.post_process_masks(out.pred_masks, inp["original_sizes"], inp["reshaped_input_sizes"], binarize=False)[0][0]
        v = torch.sigmoid(lg[int(out.iou_scores[0, 0].argmax())]).numpy() * alpha
        core = v > 0.5
        lab, n = label(core)
        if n > 1: core = lab == (1 + int(np.argmax([(lab == i).sum() for i in range(1, n + 1)])))   # the part itself, not stray bits
        if core.sum() < 20 or core.sum() > 0.3 * (alpha > 0.5).sum(): masks.append(None); continue     # nothing, or half the character
        grow = 3 if p["kind"] == "tongue" else 7                                                    # take its outline and glow with it
        masks.append(np.clip(gaussian_filter(maximum_filter(core.astype(np.float32), size=grow), 1.0), 0, 1))
    return masks


def character_frames(im, parts, mouth=None, frames_n=32):
    """The idle loop and the talking loop of a cut-out character. `parts`: [{kind, box, joint, tip}] in fractions; `mouth`: {box, line}
    as for talk_frames (None: no talking row). Returns (idle frames, talking frames)."""
    import math, numpy as np
    from scipy.ndimage import gaussian_filter
    im = im.convert("RGBA"); w0, h0 = im.size; pad = round(max(w0, h0) * 0.09)
    W, H = w0 + 2 * pad, h0 + 2 * pad
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0)); canvas.paste(im, (pad, pad))
    A = _defringe(np.asarray(canvas).astype(np.float32) / 255.0)
    P = np.dstack([A[..., :3] * A[..., 3:], A[..., 3:]])
    shift = lambda q: [(q[0] * w0 + pad) / W, (q[1] * h0 + pad) / H]
    parts = [{**p, "box": shift(p["box"][:2]) + shift(p["box"][2:]), "joint": shift(p["joint"]), "tip": shift(p["tip"])} for p in parts]
    rgb = Image.new("RGB", (W, H), (128, 128, 128)); rgb.paste(canvas, (0, 0), canvas)
    masks = _part_masks(rgb, A[..., 3], parts, W, H) if parts else []
    rigs = [(p, m) for p, m in zip(parts, masks) if m is not None]
    X, Y = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32))

    def sample(img, sx, sy):
        x0 = np.clip(np.floor(sx).astype(int), 0, W - 1); y0 = np.clip(np.floor(sy).astype(int), 0, H - 1)
        x1, y1 = np.clip(x0 + 1, 0, W - 1), np.clip(y0 + 1, 0, H - 1); fx, fy = (sx - np.floor(sx))[..., None], (sy - np.floor(sy))[..., None]
        out = img[y0, x0] * (1 - fx) * (1 - fy) + img[y0, x1] * fx * (1 - fy) + img[y1, x0] * (1 - fx) * fy + img[y1, x1] * fx * fy
        return out * ((sx >= 0) & (sx <= W - 1) & (sy >= 0) & (sy <= H - 1))[..., None]

    def geometry(p):
        px, py = p["joint"][0] * W, p["joint"][1] * H; tx, ty = p["tip"][0] * W, p["tip"][1] * H
        return px, py, tx, ty, max(4.0, math.hypot(tx - px, ty - py))

    def weight(p, lo, span):                                             # 0 at the joint, rising to 1 further out
        px, py, _, _, L = geometry(p)
        x = np.clip((np.hypot(X - px, Y - py) / L - lo) / span, 0, 1); return x * x * (3 - 2 * x)

    def bend(layer, p, deg, stretch):
        px, py, tx, ty, L = geometry(p); ux, uy = (tx - px) / L, (ty - py) / L
        dx, dy = X - px, Y - py; wgt = weight(p, 0.12, 0.6); a = -math.radians(deg) * wgt
        c, s = np.cos(a), np.sin(a); qx, qy = c * dx - s * dy, s * dx + c * dy
        if stretch:
            along = qx * ux + qy * uy; k = 1 + stretch * wgt; qx, qy = qx - along * ux * (1 - 1 / k), qy - along * uy * (1 - 1 / k)
        return sample(layer, qx + px, qy + py)

    def fill(prem, hole, steps=60):                                      # paint what was under a part from around it
        out, known = prem.copy(), ((1 - hole) * (prem[..., 3] > 0.5)).astype(np.float32)
        for _ in range(steps):
            acc, cnt = np.zeros_like(out), np.zeros(out.shape[:2], np.float32)
            for sh in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                k = np.roll(known, sh, axis=(0, 1)); acc += np.roll(out, sh, axis=(0, 1)) * k[..., None]; cnt += k
            grow = (known == 0) & (cnt > 0) & (hole > 0.02)
            out[grow] = (acc / np.maximum(cnt, 1)[..., None])[grow]; known = np.maximum(known, grow.astype(np.float32))
        return out

    holes = [m * weight(p, 0.18, 0.35) for p, m in rigs]                 # only what really leaves its place is lifted from the body
    lift = np.clip(sum((h for (p, _), h in zip(rigs, holes) if p["kind"] != "tongue"), np.zeros((H, W), np.float32)), 0, 1)
    base = P * (1 - lift)[..., None]
    for (p, _), h in zip(rigs, holes):
        if p["kind"] == "tongue": base = fill(base * (1 - h)[..., None], h)
    layers = [P * m[..., None] for _, m in rigs]
    order = sorted(range(len(rigs)), key=lambda i: rigs[i][0]["kind"] == "tongue")      # the tongue in front
    idle = []
    for k in range(frames_n):
        t = k / frames_n; img = base.copy()
        for i in order:
            p = rigs[i][0]; deg, cyc, st = MOTION.get(p["kind"], MOTION["other"]); ph = (sum(map(ord, p.get("name", ""))) % 100) / 100 * 2 * math.pi if p["kind"] == "ear" else 0.0
            if p["kind"] == "ear" and p["joint"][0] > 0.5: deg = -deg                    # ears flop outwards, each its own way
            lay = bend(layers[i], p, deg * math.sin(2 * math.pi * cyc * t + ph), st * (0.5 + 0.5 * math.sin(2 * math.pi * cyc * t + ph + 1)) if st else 0)
            img = lay + img * (1 - lay[..., 3:])
        br = 0.012 * math.sin(2 * math.pi * t)                           # breathing: a little taller, feet planted
        img = sample(img, X, H - 1 - (H - 1 - Y) / (1 + br))
        a = img[..., 3:]; col = np.where(a > 1e-4, img[..., :3] / np.maximum(a, 1e-4), 0)
        idle.append(Image.fromarray((np.dstack([col, a]) * 255).clip(0, 255).astype(np.uint8), "RGBA"))
    talking = []
    if mouth:
        pm = {"mouth": [(mouth["box"][0] * w0 + pad) / W, (mouth["box"][1] * h0 + pad) / H, (mouth["box"][2] * w0 + pad) / W, (mouth["box"][3] * h0 + pad) / H],
              "line": [shift(q) for q in mouth["line"]] if mouth.get("line") else None, "open": mouth.get("open", 0.018) * h0 / H}
        for k, f in enumerate(idle):                                     # the same loop, with the jaw going about four times a second
            s = 0.5 - 0.5 * math.cos(2 * math.pi * 8 * k / frames_n)
            talking.append(_jaw(f, pm, s))
    boxes = [f.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox() for f in idle + talking]
    boxes = [b for b in boxes if b]
    if boxes:
        b = (min(x[0] for x in boxes), min(x[1] for x in boxes), max(x[2] for x in boxes), max(x[3] for x in boxes))
        idle, talking = [f.crop(b) for f in idle], [f.crop(b) for f in talking]
    return idle, talking


def _jaw(im, p, s):
    """One talking frame: the jaw opened by s (0 closed, 1 fully open). Same mouth parameters as talk_frames."""
    import numpy as np
    a = np.asarray(im.convert("RGBA")).astype(np.float32); H, W = a.shape[:2]
    x0, y0, x1, y1 = _box(p.get("mouth"), W, H, "mouth box")
    pts = p.get("line") or [[x0 / W, y0 / H], [x1 / W, y0 / H]]
    xs = np.array([float(q[0]) * W for q in pts]); ys = np.array([float(q[1]) * H for q in pts]); o = np.argsort(xs); xs, ys = xs[o], ys[o]
    X, Y = np.meshgrid(np.arange(W, dtype=np.float32), np.arange(H, dtype=np.float32)); yl = np.interp(X, xs, ys)
    cx, half = (xs[0] + xs[-1]) / 2, (xs[-1] - xs[0]) / 2 + 2
    wx = np.clip(1 - ((X - cx) / half) ** 2, 0, 1) ** 2; wy = np.clip((y1 - Y) / np.maximum(y1 - yl, 1), 0, 1) * (Y >= yl - 1)
    d = s * float(p.get("open", 0.018)) * H * wx * wy; sy = Y - d
    r0 = np.clip(np.floor(sy).astype(int), 0, H - 1); r1 = np.clip(r0 + 1, 0, H - 1); f = (sy - np.floor(sy))[..., None]; cols = X.astype(int)
    out = a[r0, cols] * (1 - f) + a[r1, cols] * f
    k = np.clip((yl - sy) / 1.5, 0, 1)[..., None] * ((sy < yl) & (d > 0.3))[..., None]
    out = out * (1 - k) + np.array([38, 18, 24, 255], np.float32) * k
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGBA")


def _sprite_rows(rows):
    """Frames of several rows (each the same length) as one sheet: row r, frame k at (k * w, r * h). Scaled down to fit WebP's limit."""
    w, h = rows[0][0].size; n = len(rows[0])
    scale = min(1.0, SPRITE_MAX_W / (w * n)); fw, fh = max(1, int(w * scale)), max(1, int(h * scale))
    sheet = Image.new("RGBA", (fw * n, fh * len(rows)), (0, 0, 0, 0))
    for r, row in enumerate(rows):
        for k, f in enumerate(row): sheet.paste(f.convert("RGBA").resize((fw, fh), Image.LANCZOS), (k * fw, r * fh))
    buf = io.BytesIO(); sheet.save(buf, "WEBP", quality=90, method=5)
    return buf.getvalue(), fw, fh


# ---------------------------------------------------------------- actors: a character that speaks and acts on cue
# A character (an animated "character" image that speaks as, say, Spotter) is an actor. A script gives it lines ("Spotter say: …") and
# things to do ("Spotter animate: wave"). What it can do is either a clip of it doing that (an item whose clip is linked under the
# character's `actions`) or a built-in motion of the picture itself (jump, nod, shake, bounce...). The words in a script are matched to
# an action by meaning ("wiggle his tail" is `wag`), so nobody has to learn the exact names.

MOTIONS = {  # built-in motions of the character's picture: name -> seconds. The shapes live in compose.MOTION_JS.
    "jump": 1.1, "hop": 0.6, "nod": 1.1, "shake": 1.2, "bounce": 1.4, "wiggle": 1.2, "spin": 1.2,
}
SYNONYMS = {  # canonical action -> words or phrases that mean it
    "wave": "wave waves waving hello hi hey greet greets greeting goodbye bye welcome",
    "wink": "wink winks winking",
    "laugh": "laugh laughs laughing giggle giggles chuckle chuckles lol haha laughter",
    "jump": "jump jumps jumping leap leaps",
    "hop": "hop hops hopping",
    "wag": "wag wags wagging waggle wiggle wiggles tail",
    "think": "think thinks thinking ponder ponders hmm wonder puzzled curious",
    "nod": "nod nods nodding agree agrees approve yes",
    "shake": "shake shakes disagree nope no",
    "bounce": "bounce bounces bouncing excited dance dances dancing party celebrate celebrates cheer cheers hooray yay",
    "wiggle": "wiggle wiggles wiggling",
    "spin": "spin spins twirl twirls turn around",
    "celebrate": "celebrate celebrates cheer cheers hooray yay party dance dances dancing",
    "point": "point points present presents gesture",
    "sit": "sit sits", "sleep": "sleep sleeps nap yawn",
}


def actor(name):
    """The library character that speaks as `name`, or None."""
    n = str(name or "").strip().casefold()
    return next((i for i in listing() if n and str(i.get("speaker", "")).casefold() == n and (i.get("animated") or {}).get("mode") == "character"), None)


def actor_voice(name):
    """What the library says this character's voice is (a name like 'Puppy'), or None."""
    it = actor(name); return it.get("voice") if it else None


def actions_of(it):
    """{action name: seconds} a character can do: its own clips first, then the built-in motions it doesn't have a clip for."""
    out = dict(MOTIONS)
    for k, cid in (it.get("actions") or {}).items():
        c = get(cid)
        if c and c["format"] in VIDEO_FORMATS: out[k] = c.get("seconds", 2.0)
    return out


def match_actions(text, available):
    """The actions (from `available`) that a phrase like 'wiggle his tail and wink' asks for, in the order it asks, at most three."""
    words = re.findall(r"[a-z']+", str(text).lower()); joined = " " + " ".join(words) + " "
    found = []                                                          # (position in the text, action)
    for act in available:
        keys = set(SYNONYMS.get(act, "").split()) | {act.lower(), act.lower() + "s", act.lower() + "ing"}
        pos = [i for i, w in enumerate(words) if w in keys]
        for phrase in [x for x in keys if " " in x]:
            if f" {phrase} " in joined: pos.append(joined.index(f" {phrase} "))
        if pos: found.append((min(pos), act))
    # words that name one thing must not also pick a loose neighbour: "wiggle his tail" is a wag (wag mentions tail), not a wiggle,
    # when the character has a wag clip; so when two actions answer the same word, the character's own clip wins
    ordered = [a for _, a in sorted(found)]
    words_used = {}
    for act in ordered:
        for w in set(SYNONYMS.get(act, "").split()) | {act}:
            if w in words: words_used.setdefault(w, []).append(act)
    drop = set()
    for w, acts in words_used.items():
        if len(acts) > 1:
            own = [a for a in acts if a not in MOTIONS]
            if own: drop |= {a for a in acts if a in MOTIONS}
    return [a for a in ordered if a not in drop][:3]


def link_action(actor_id, name, clip_id, start=None, end=None, status=None):
    """Make a clip (or a part of it, from `start` to `end` seconds) one of a character's actions, under a name like 'wave'. A clip filmed on a green
    screen is cut out first, in the same frame as the character, so the character doesn't shift when it switches to the action."""
    name = re.sub(r"[^a-z0-9 -]", "", str(name or "").lower()).strip()[:24]
    if not name: raise MediaError("Give the action a name, like wave or wink.")
    it, clip = get(actor_id), get(clip_id)
    if it is None or (it.get("animated") or {}).get("mode") != "character": raise MediaError("Pick a talking character (one that has been brought to life or made from a clip) to add the action to.")
    if clip is None or clip["format"] not in VIDEO_FORMATS: raise MediaError("An action is a video clip. Upload the clip first.")
    if clip.get("transparent"):
        if start is not None or end is not None: clip = video_part(clip, {"start": start or 0, "end": end if end is not None else clip.get("seconds", 0)}, name=f"{it['name']} {name}")
    else:
        if status: status("Cutting the clip out to match the character…")
        clip = video_cutout(clip, {"like": it.get("parent"), "start": start or 0, "end": end if end is not None else clip.get("seconds", 0)}, name=f"{it['name']} {name}", status=status)
    with _lock:
        items = listing(); it = next(i for i in items if i["id"] == actor_id)
        it.setdefault("actions", {})[name] = clip["id"]
        if clip["id"] != clip_id: next(i for i in items if i["id"] == clip["id"])["action_of"] = actor_id          # made for this action: it lives with the character
        _save(items); return it


def unlink_action(actor_id, name):
    with _lock:
        items = listing(); it = next((i for i in items if i["id"] == actor_id), None)
        if it is None: raise MediaError("That character isn't in the library.")
        (it.get("actions") or {}).pop(name, None)
        if not it.get("actions"): it.pop("actions", None)
        _save(items); return it


def cast_for(module):
    """What the page needs to know about the characters acting in a module: for each actor its clips and durations, what each slide
    makes it do and when (resolved to real actions), and the actions a script asks for that the character can't do.
    Returns {"actors": {name: {"item": id, "actions": {action: {"kind": "clip"|"motion", "seconds": s}}}}, "acts": {slide id: {at: [[name, action]]}},
    "clips": {name: {action,...}}, "by_slide": {slide id: {name: {action,...}}}, "unknown": [(slide id, name, phrase)]}; nothing in it when no slide acts."""
    from html2mp4.compose import scene_ids
    ids = scene_ids(module); rows = ([(module.intro_acts, module.intro_speakers)] if module.intro else []) + [(s.acts, s.speakers) for s in module.slides]
    out = {"actors": {}, "acts": {}, "clips": {}, "by_slide": {}, "unknown": []}
    for sid, (acts, _sp) in zip(ids, rows):
        for a in acts:
            it = actor(a["who"])
            have = actions_of(it) if it else dict(MOTIONS)
            found = match_actions(a["do"], list(have))
            if not found:
                if it is None or not re.fullmatch(r"\s*(?:idle|stand|appear|smile|hello there|stay)\s*", a["do"], re.I): out["unknown"].append((sid, a["who"], a["do"]))
                continue
            for act in found:
                clip = it and (it.get("actions") or {}).get(act) and get(it["actions"][act])
                kind = "clip" if clip and clip["format"] in VIDEO_FORMATS else "motion"
                ent = out["actors"].setdefault(a["who"], {"item": it["id"] if it else None, "actions": {}})
                ent["actions"][act] = {"kind": kind, "seconds": float(have[act])}
                out["by_slide"].setdefault(sid, {}).setdefault(a["who"], set())               # a character that acts on a slide is wrapped there (see resolve)
                if kind == "clip":
                    out["clips"].setdefault(a["who"], set()).add(act)
                    out["by_slide"][sid][a["who"]].add(act)                                       # a slide carries only the clips it plays
                out["acts"].setdefault(sid, {}).setdefault(str(a["at"]), []).append([a["who"], act])
    return out


# ---------------------------------------------------------------- video clips
# A clip is kept as WebM (VP9), whatever was uploaded: the video renderer's browser plays it, it can carry transparency, and with a
# keyframe every half second the renderer can show any exact moment of it. Clips are silent on a slide (the narration is the
# soundtrack), so their sound isn't kept, but when it was speech, when it spoke is: that is how a talking character is made from one.

VIDEO_FORMATS = ("webm",)
VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm", ".mkv")
MAX_VIDEO_UPLOAD, MAX_VIDEO_SECONDS, VIDEO_MAX_SIDE = 200 * 1024 * 1024, 60, 1280


def is_video(raw, filename=""):
    return pathlib.Path(filename).suffix.lower() in VIDEO_EXT or raw[4:8] == b"ftyp" or raw[:4] == b"\x1a\x45\xdf\xa3"


def _ffmpeg():
    from html2mp4.cli import FFMPEG
    return FFMPEG


def _probe(src):
    """(width, height, seconds, fps, has sound) of a video file, read from ffmpeg's own report."""
    import subprocess
    err = subprocess.run([_ffmpeg(), "-hide_banner", "-i", str(src)], capture_output=True, text=True).stderr
    d = re.search(r"Duration:\s*(\d+):(\d+):([\d.]+)", err); v = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", err)
    if not d or not v: raise MediaError("That file isn't a video this app can read (use MP4, MOV or WebM).")
    fps = re.search(r"([\d.]+)\s*fps", err)
    secs = int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3))
    return int(v.group(1)), int(v.group(2)), secs, float(fps.group(1)) if fps else 24.0, "Audio:" in err


def _speech(src, seconds):
    """When the clip's sound is speech-loud, as [[start, end], ...] seconds (gaps under a third of a second are joined)."""
    import subprocess, numpy as np
    raw = subprocess.run([_ffmpeg(), "-v", "error", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, np.int16).astype(np.float32) / 32768
    if not len(a): return []
    hop = 800; rms = np.array([np.sqrt(np.mean(a[i:i + hop] ** 2)) for i in range(0, len(a) - hop, hop)])
    if not len(rms) or rms.max() < 0.01: return []
    on = rms > max(0.02, 0.25 * np.percentile(rms, 95))
    out, start = [], None
    for k, x in enumerate(list(on) + [False]):
        t = k * hop / 16000
        if x and start is None: start = t
        if not x and start is not None: out.append([round(start, 2), round(t, 2)]); start = None
    joined = []
    for a0, b0 in out:
        if joined and a0 - joined[-1][1] < 0.35: joined[-1][1] = b0
        else: joined.append([a0, b0])
    return [x for x in joined if x[1] - x[0] >= 0.3]


def add_video(raw, filename="clip", name=None, kind=None, description=""):
    import subprocess, tempfile
    if len(raw) > MAX_VIDEO_UPLOAD: raise MediaError("That video is too large (200 MB at most).")
    stem = re.sub(r"[_\-]+", " ", pathlib.Path(filename).stem).strip() or "Clip"
    with tempfile.TemporaryDirectory() as td:
        src = pathlib.Path(td) / ("in" + (pathlib.Path(filename).suffix.lower() or ".mp4")); src.write_bytes(raw)
        w, h, secs, fps, sound = _probe(src)
        if secs > MAX_VIDEO_SECONDS: raise MediaError(f"Keep clips to {MAX_VIDEO_SECONDS} seconds or shorter (this one is {secs:.0f} s). Trim it first.")
        speech = _speech(src, secs) if sound else []
        out = pathlib.Path(td) / "out.webm"
        subprocess.run([_ffmpeg(), "-y", "-v", "error", "-i", str(src), "-an", "-vf",
                        f"scale='if(gt(iw,ih),min({VIDEO_MAX_SIDE},iw),-2)':'if(gt(iw,ih),-2,min({VIDEO_MAX_SIDE},ih))':flags=lanczos,fps={min(30, round(fps))}",
                        "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "32", "-row-mt", "1", "-deadline", "good", "-cpu-used", "4",
                        "-g", str(max(6, min(30, round(fps)) // 2)), "-pix_fmt", "yuv420p", str(out)], check=True)
        w2, h2, secs2, fps2, _ = _probe(out)
        return _store(out.read_bytes(), "webm", w2, h2, False, name or stem, kind if kind in KINDS else "other", description, None,
                      f"uploaded video ({filename})", None, {"seconds": round(secs2, 2), "fps": round(fps2), "speech": speech, "poster": min(1.0, secs2 / 3)})


def video_frames(item, start=0.0, end=None, fps=None, max_side=None):
    """Frames of a clip from `start` to `end` seconds at `fps` (RGBA when the clip has transparency)."""
    import subprocess, numpy as np
    end = item.get("seconds", 0) if end is None else end; fps = fps or item.get("fps", 24)
    w, h = item["w"], item["h"]
    if max_side and max(w, h) > max_side: s = max_side / max(w, h); w, h = max(2, round(w * s / 2) * 2), max(2, round(h * s / 2) * 2)
    alpha = item.get("transparent")
    dec = ["-c:v", "libvpx-vp9"] if alpha else []                      # ffmpeg's own VP9 decoder drops transparency; libvpx keeps it
    raw = subprocess.run([_ffmpeg(), "-v", "error", *dec, "-ss", f"{start:.3f}", "-i", str(path(item)), "-t", f"{max(0.05, end - start):.3f}",
                          "-vf", f"fps={fps},scale={w}:{h}:flags=lanczos", "-f", "rawvideo", "-pix_fmt", "rgba" if alpha else "rgb24", "-"],
                         capture_output=True, check=True).stdout
    n = 4 if alpha else 3; size = w * h * n
    return [Image.fromarray(np.frombuffer(raw[i:i + size], np.uint8).reshape(h, w, n), "RGBA" if alpha else "RGB") for i in range(0, len(raw) - size + 1, size)]


def video_frame(item, t=0.0):
    fr = video_frames(item, t, t + 0.2, fps=10)
    if not fr: fr = video_frames(item, 0, 0.2, fps=10)
    if not fr: raise MediaError("Couldn't read a picture from that clip.")
    return fr[0]


def _encode_webm(frames, fps, alpha):
    """Frames -> a WebM clip (VP9, with transparency when `alpha`)."""
    import subprocess, tempfile
    w, h = frames[0].size; w2, h2 = w - w % 2, h - h % 2
    with tempfile.TemporaryDirectory() as td:
        out = pathlib.Path(td) / "out.webm"
        p = subprocess.Popen([_ffmpeg(), "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{w2}x{h2}", "-r", str(fps), "-i", "-",
                              "-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "30", "-row-mt", "1", "-deadline", "good", "-cpu-used", "4",
                              "-g", str(max(6, fps // 2)), "-pix_fmt", "yuva420p" if alpha else "yuv420p", "-auto-alt-ref", "0", str(out)], stdin=subprocess.PIPE)
        for f in frames: p.stdin.write(f.convert("RGBA").crop((0, 0, w2, h2)).tobytes())
        p.stdin.close(); p.wait()
        if p.returncode: raise MediaError("Couldn't encode the clip.")
        return out.read_bytes(), w2, h2


def _cut_frames(frames, box=None, status=None, label="Removing the background"):
    """Remove the background from every frame (the subject found in each), then crop all of them to the same box."""
    out = []
    key = None if box else green_screen_colour(frames[0])                 # filmed on a green screen: key it (fast and clean); otherwise cut each frame out
    for k, f in enumerate(frames):
        if status and k % 6 == 0: status(f"{label}: frame {k + 1} of {len(frames)}…")
        out.append(chroma_key(f, key) if key else remove_background(f, box))
    boxes = [f.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox() for f in out]
    boxes = [b for b in boxes if b]
    if not boxes: raise MediaError("Couldn't find the subject in the clip.")
    m = 6; W, H = out[0].size
    b = (max(0, min(x[0] for x in boxes) - m), max(0, min(x[1] for x in boxes) - m), min(W, max(x[2] for x in boxes) + m), min(H, max(x[3] for x in boxes) + m))
    cut = [f.crop(b) for f in out]
    return [_fade_cut_edges(f, b, (W, H)) for f in cut]


def green_screen_colour(im):
    """The colour of a green-screen backdrop, read from the picture's edges (any shade of green), or None when the edges aren't green."""
    import numpy as np
    a = np.asarray(im.convert("RGB")).astype(np.float32) / 255; h, w = a.shape[:2]; m = max(2, round(0.03 * min(h, w)))
    rim = np.concatenate([a[:m].reshape(-1, 3), a[-m:].reshape(-1, 3), a[:, :m].reshape(-1, 3), a[:, -m:].reshape(-1, 3)])
    green = (rim[:, 1] - np.maximum(rim[:, 0], rim[:, 2]) > 0.25) & (rim[:, 1] > 0.45)
    return tuple(float(x) for x in np.median(rim[green], axis=0)) if green.mean() > 0.5 else None


def _main_subject(alpha, keep=0.02, grow=4):
    """Keep only the main subject of a matte: parts at least `keep` of the biggest part's size (a detached ear or tail tip is kept), plus the soft
    edge around them; specks, sparkles and watermarks are dropped."""
    import numpy as np
    from scipy import ndimage
    solid = alpha > 0.2
    lab, n = ndimage.label(solid)
    if n <= 1: return alpha
    sizes = ndimage.sum(solid, lab, range(1, n + 1)); big = np.isin(lab, [i + 1 for i, z in enumerate(sizes) if z >= keep * sizes.max()])
    near = ndimage.binary_dilation(big, iterations=grow)
    return np.where(near, alpha, 0.0)


def chroma_key(im, key=None, lo=0.30, hi=0.72, main_only=True):
    """A frame filmed in front of a green screen as an RGBA cut-out: a soft matte (so fur and motion blur keep their edges) and the
    green spill taken out of the colours. `key` is the screen's colour (found from the edges when not given)."""
    import numpy as np
    a = np.asarray(im.convert("RGB")).astype(np.float32) / 255
    kr, kg, kb = key or green_screen_colour(im) or (0.0, 1.0, 0.0)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    # how green a pixel is relative to its own brightness, against how green the screen is: a shadow on the screen is as green as the screen
    ex = g - np.maximum(r, b)
    t = (ex / np.maximum(g, 1e-3)) / max((kg - max(kr, kb)) / kg, 1e-3)
    alpha = 1.0 - np.clip((t - lo) / (hi - lo), 0.0, 1.0); alpha = alpha * alpha * (3 - 2 * alpha)
    alpha[alpha < 0.03] = 0.0
    if main_only: alpha = _main_subject(alpha)
    # edge pixels are a mix of the character and the screen: take the screen's share out, then cap what green is left
    fg = a.copy(); soft = (alpha > 0.0) & (alpha < 1.0)
    for c, k in enumerate((kr, kg, kb)): fg[..., c] = np.where(soft, (a[..., c] - (1 - alpha) * k) / np.maximum(alpha, 1e-3), a[..., c])
    fg = np.clip(fg, 0, 1)
    cap = np.maximum(fg[..., 0], fg[..., 2]) + np.where(soft, 0.0, 0.02)       # edge pixels keep no green at all
    fg[..., 1] = np.minimum(fg[..., 1], cap)
    out = np.dstack([fg, alpha])
    return Image.fromarray((out * 255 + 0.5).astype(np.uint8), "RGBA")


def _fade_cut_edges(f, box, size, share=0.14):
    """A subject the camera cut off at the bottom (legs out of the frame) fades out towards it instead of ending in a hard line."""
    import numpy as np
    a = np.asarray(f).copy(); h, w = a.shape[:2]; alpha = a[..., 3].astype(np.float32)
    W, H = size
    for side, touching in (("bottom", box[3] >= H),):          # only the bottom: legs cut off fade away; a head or ears cut off stay as they are
        n = int((h if side in ("bottom", "top") else w) * share)
        if not touching or n < 2: continue
        if side in ("bottom", "top") and alpha[-1 if side == "bottom" else 0].max() < 128: continue
        if side in ("left", "right") and alpha[:, -1 if side == "right" else 0].max() < 128: continue
        ramp = np.linspace(1, 0, n) ** 1.5
        if side == "bottom": alpha[h - n:] *= ramp[:, None]
        elif side == "top": alpha[:n] *= ramp[::-1][:, None]
        elif side == "right": alpha[:, w - n:] *= ramp[None, :]
        else: alpha[:, :n] *= ramp[::-1][None, :]
    a[..., 3] = alpha.clip(0, 255).astype(np.uint8)
    return Image.fromarray(a, "RGBA")


def clip_extent(src, start=0.0, end=None, max_side=1280):
    """(box, frame size): the smallest box, in the clip's pixels, that holds the subject of a green-screen clip everywhere it goes."""
    end = src.get("seconds", 0) if end is None else end
    probe = video_frames(src, start, end, 8, max_side=max_side)
    key = green_screen_colour(probe[0]) if probe else None
    boxes = [b for b in (chroma_key(f, key).getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox() for f in probe) if b]
    if not boxes: raise MediaError("Couldn't find the subject in the clip.")
    return (min(x[0] for x in boxes), min(x[1] for x in boxes), max(x[2] for x in boxes), max(x[3] for x in boxes)), probe[0].size


def frame_around(*boxes, size, margin=0.02, side_room=0.0):
    """One frame that holds several boxes: their union, `margin` of the picture's longer side all round, and `side_room` of its width more each
    side (so a later clip with an arm out or a head back still fits), kept inside the picture."""
    W, H = size; m = round(margin * max(W, H)); r = round(side_room * W)
    return (max(0, min(b[0] for b in boxes) - m - r), max(0, min(b[1] for b in boxes) - m), min(W, max(b[2] for b in boxes) + m + r), min(H, max(b[3] for b in boxes) + m))


def _key_clip(src, start, end, fps, max_side, status=None, crop=None):
    """A clip filmed on a green screen as cut-out frames, all cropped to one box around everywhere the subject goes. A quick first pass finds that
    box; then the frames are keyed a couple of seconds at a time, so a long clip never has to sit in memory whole."""
    probe = video_frames(src, start, end, 8, max_side=max_side)
    if not probe: raise MediaError("Couldn't read that clip.")
    key = green_screen_colour(probe[0]); boxes = []
    for f in probe:
        b = chroma_key(f, key).getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
        if b: boxes.append(b)
    if not boxes: raise MediaError("Couldn't find the subject in the clip.")
    W, H = probe[0].size; m = round(0.02 * max(W, H)); del probe
    box = (max(0, min(x[0] for x in boxes) - m), max(0, min(x[1] for x in boxes) - m), min(W, max(x[2] for x in boxes) + m), min(H, max(x[3] for x in boxes) + m))
    if crop:                                      # the same frame as another cut-out, so the two line up exactly
        own = (min(x[0] for x in boxes), min(x[1] for x in boxes), max(x[2] for x in boxes), max(x[3] for x in boxes))
        if own[0] < crop[0] - 10 or own[1] < crop[1] - 10 or own[2] > crop[2] + 10 or own[3] > crop[3] + 10:
            raise MediaError("The character moves outside the frame of the clip it is meant to match (it goes further than the other clips do). Film it nearer the middle, or cut both out again without matching.")
        box = tuple(crop)
    out, t = [], start
    while t < end - 1e-6:
        if status: status(f"Cutting the character out: {t - start:.0f} of {end - start:.0f} seconds…")
        out += [chroma_key(f, key).crop(box) for f in video_frames(src, t, min(end, t + 2.0), fps, max_side=max_side)]
        t += 2.0
    return out, box, (W, H)


def video_cutout(src, params, name=None, status=None):
    """The clip with its background removed (a transparent WebM). A clip filmed on a green screen is keyed (fast, clean, the clip's own frame
    rate); any other clip has each frame cut out by Segment Anything (slow: at most 15 frames a second, 30 seconds)."""
    start = float(params.get("start", 0)); end = float(params.get("end", src.get("seconds", 0)))
    first = video_frames(src, start, start + 0.2, 10, max_side=int(params.get("max", 1280)))
    keyed = bool(first) and not params.get("box") and green_screen_colour(first[0]) is not None
    fps = int(params.get("fps") or (min(24, round(src.get("fps", 24))) if keyed else min(15, round(src.get("fps", 24)))))
    crop = frame = None
    if keyed:
        like = get(params["like"]) if params.get("like") else None
        if params.get("crop"): crop = [int(x) for x in params["crop"]]                          # an exact frame, in the clip's pixels
        elif like and like.get("crop") and like.get("frame") == [first[0].width, first[0].height]: crop = like["crop"]
        elif params.get("like"): raise MediaError("That clip can't be matched to the character: it was filmed at a different size. Film it the same way (same camera, same distance).")
        elif params.get("side_room"):
            own, size = clip_extent(src, start, end, int(params.get("max", 1280))); crop = frame_around(own, size=size, side_room=float(params["side_room"]))
        fr, crop, frame = _key_clip(src, start, end, fps, int(params.get("max", 1280)), status, crop)
    else:
        fr = video_frames(src, start, end, fps, max_side=int(params.get("max", 1280)))
        if len(fr) > 15 * 30: raise MediaError("Cut out 30 seconds of a clip at most at a time (choose a start and end).")
        fr = _cut_frames(fr, params.get("box"), status)
    data, w, h = _encode_webm(fr, fps, True)
    return _store(data, "webm", w, h, True, name or f"{src['name']} (cut out)", params.get("kind") or src["kind"], src.get("description", ""),
                  src["id"], f"remove_background of {src['name']}", None, {"seconds": round(len(fr) / fps, 2), "fps": fps, "poster": 0.0,
                  "speech": [[max(0, a - start), b - start] for a, b in src.get("speech", []) if b > start and a < end],
                  **({"crop": [int(x) for x in crop], "frame": list(frame)} if crop else {})})


def video_part(src, params, name=None):
    """A part of a clip, from `start` to `end` seconds, as a clip of its own (a cut-out clip stays a cut-out)."""
    secs = float(src.get("seconds", 0)); start = float(params.get("start", 0)); end = float(params.get("end", secs))
    if not 0 <= start < end <= secs + 0.05: raise MediaError(f"Choose a part of the clip between 0 and {secs:g} seconds, like start 6.9 and end 7.7.")
    if end - start < 0.3: raise MediaError("A part of a clip needs to be at least a third of a second long.")
    fps = int(src.get("fps", 24)); fr = video_frames(src, start, end, fps)
    if not fr: raise MediaError("Couldn't read that part of the clip.")
    data, w, h = _encode_webm([f.convert("RGBA") for f in fr], fps, bool(src.get("transparent")))
    return _store(data, "webm", w, h, bool(src.get("transparent")), name or f"{src['name']} ({start:g}–{end:g} s)", params.get("kind") or src["kind"],
                  src.get("description", ""), src["id"], f"part of {src['name']}", None,
                  {"seconds": round(len(fr) / fps, 2), "fps": fps, "poster": 0.0,
                   "speech": [[max(0, a - start), min(end, b) - start] for a, b in src.get("speech", []) if b > start and a < end],
                   **({"crop": src["crop"], "frame": src["frame"]} if src.get("crop") else {})})


def _longest(spans, lo, hi):
    spans = [(max(lo, a), min(hi, b)) for a, b in spans if min(hi, b) - max(lo, a) > 0]
    return max(spans, key=lambda x: x[1] - x[0]) if spans else None


def _busiest(src, a, b, n, fps):
    """The start (in seconds) of the `n` frames between `a` and `b` where the picture moves the most: for a clip of someone talking, where the mouth
    works hardest."""
    import numpy as np
    best, at = -1.0, a
    t = a
    while t + n / fps <= b + 1e-6:
        fr = video_frames(src, t, t + n / fps, fps, max_side=200)[:n]
        if len(fr) >= 3:
            g = [np.asarray(f.convert("L"), np.float32) * (np.asarray(f.convert("RGBA").getchannel("A"), np.float32) / 255) for f in fr]     # luma, where there is a picture
            move = float(np.mean([np.abs(g[i + 1] - g[i]).mean() for i in range(len(g) - 1)]))
            if move > best: best, at = move, t
        t += 0.2
    return at


def video_character(src, params, name=None, status=None):
    """A talking character made from a clip of it speaking: the idle loop from where it is quiet, the talking loop from where it speaks (found
    from the clip's sound unless given as `idle`/`talk` [start, end]). Each loop plays forward then back, so it joins up smoothly. The picture is
    the clip's own frame, so actions cut from the same clip line up with it exactly. A clip that isn't cut out yet is cut out first."""
    if not src.get("transparent"):
        if status: status("Cutting the character out…")
        cut = video_cutout(src, {"max": int(params.get("max", 1280)), "box": params.get("box"), "side_room": params.get("side_room", 0.08)}, None, status)
        return video_character(cut, params, name, status)
    secs = src.get("seconds", 0); speech = src.get("speech") or []
    talk = params.get("talk") or (_longest(speech, 0, secs) if speech else None)
    if not talk: raise MediaError("Couldn't tell when the character speaks in this clip (it has no speech). Say which seconds it talks, e.g. talk 4 to 8.")
    quiet, t0 = [], 0.0
    for a, b in sorted(speech) + [[secs, secs]]:
        if a - t0 > 0: quiet.append((t0, a))
        t0 = max(t0, b)
    # the quiet stretch nearest the speech: the character holds much the same pose there, so the switch between loops is gentle
    gap = lambda q: max(talk[0] - q[1], q[0] - talk[1], 0)
    idle = params.get("idle") or min((q for q in quiet if q[1] - q[0] >= 0.6), key=gap, default=_longest(quiet, 0, secs))
    if not idle or idle[1] - idle[0] < 0.4: idle = (max(0, talk[0] - 1.6), talk[0])
    fps, per = int(params.get("fps", 12)), int(params.get("frames", 10))             # frames each way of a loop (few, so each can be sharp)
    def loop(a, b, busiest=False):
        n = min(per, max(4, int((b - a) * fps)))
        a2 = _busiest(src, a, b, n, fps) if busiest and b - a > n / fps + 0.25 else max(a, (a + b) / 2 - n / fps / 2)
        fr = video_frames(src, a2, a2 + (n + 1) / fps, fps)[:n]                    # (a frame of slack: a window off the clip's frame grid gives one fewer)
        return fr + fr[-2:0:-1]                                                    # forward, then back (without repeating the ends)
    if status: status("Making the idle and talking loops…")
    idle_f, talk_f = loop(*idle), loop(*talk, busiest=True)
    k = min(len(idle_f), len(talk_f)); idle_f, talk_f = idle_f[:k], talk_f[:k]
    data, fw, fh = _sprite_rows([idle_f, talk_f])
    return _store(data, "webp", fw, fh, True, name or f"{src['name']} (character)", params.get("kind") or "mascot", src.get("description", ""),
                  src["id"], f"character from {src['name']}", {"frames": k, "fps": fps, "mode": "character", "rows": 2},
                  {**({"speaker": params["speaker"]} if params.get("speaker") else {}), **({"crop": src["crop"], "frame": src["frame"]} if src.get("crop") else {})})
