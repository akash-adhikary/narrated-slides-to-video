"""Modules on disk: a script, its designed HTML, and every version along the way.

    ~/Downloads/Narrated Videos/Modules/<name>/
        project.json     name (the label you gave the module), title (the video's own title), script, draft, versions
        chat.json        the conversation with the script assistant, kept with the module
        script.txt       the current script
        module.html      the current module (what the video is made from)
        versions/v1.html, v1.json ...   every saved design, and the slide designs it came from
"""
import json, os, pathlib, re, shutil, time

MODULES = pathlib.Path(os.environ.get("HTML2MP4_MODULES", pathlib.Path(os.environ.get("HTML2MP4_OUTPUT", pathlib.Path.home() / "Downloads" / "Narrated Videos")) / "Modules"))


def slugify(text):
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")[:60] or "module"


def folder(pid): return MODULES / re.sub(r"[^\w\-]", "", pid)


def _read(pid):
    try: p = json.loads((folder(pid) / "project.json").read_text())
    except (FileNotFoundError, ValueError): return None
    p.setdefault("name", p.get("title") or p["id"])                  # modules made before names existed are called what their video is
    return p


def _write(p):
    f = folder(p["id"]); f.mkdir(parents=True, exist_ok=True)
    (f / "project.json").write_text(json.dumps(p, indent=1))


NUMBER = re.compile(r"^\s*(\d+)\s*[·.:\-–—)]\s*")


def _names(exclude=None):
    return [p["name"] for p in map(_read, [d.name for d in MODULES.iterdir() if d.is_dir()] if MODULES.exists() else []) if p and p["id"] != exclude]


def name_taken(name, exclude=None):
    return name.strip().casefold() in {n.strip().casefold() for n in _names(exclude)}


def unique_name(name):
    base, n = name.strip(), 2
    while name_taken(name): name, n = f"{base} ({n})", n + 1
    return name


def clean_name(name):
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    if not name: raise ValueError("Give the module a name.")
    if len(name) > 80: raise ValueError("Keep the name to 80 characters or fewer.")
    return name


def video_title(name):
    """The name without its number ("08 · Interviewing" -> "Interviewing"): where a new module's script starts."""
    return NUMBER.sub("", name).strip() or name


def create(title, script_text, batch="", name=None):
    """Start a project; the id is the folder name, made unique. `name` is the label shown in lists, URLs and files (the title by default)."""
    name = unique_name(clean_name(name or title))
    base, pid, n = slugify(name), slugify(name), 2
    while folder(pid).exists(): pid, n = f"{base}-{n}", n + 1
    p = {"id": pid, "name": name, "title": title, "script": script_text, "created": time.time(), "updated": time.time(), "current": 0,
         "versions": [], "feedback": [], "batch": batch}
    _write(p); (folder(pid) / "script.txt").write_text(script_text)
    return p


def get(pid): return _read(pid)


def listing(batch=None):
    out = []
    if MODULES.exists():
        for d in MODULES.iterdir():
            p = _read(d.name) if d.is_dir() else None
            if p and (batch is None or p.get("batch", "") == batch):
                out.append({k: p[k] for k in ("id", "name", "title", "created", "updated", "current", "batch") if k in p}
                           | {"versions": len(p["versions"]), "designed": bool(p["versions"])})
    return sorted(out, key=lambda x: -x["updated"])


def rename(pid, name):
    p = _read(pid); name = clean_name(name)
    if name_taken(name, exclude=pid): raise ValueError(f"You already have a module called “{name}”.")
    p["name"] = name; p["updated"] = time.time(); _write(p)
    return p


def working_script(p):
    """The text in the script box: what was last saved while writing, else the script of the last design."""
    return p["draft"] if p.get("draft") is not None else p["script"]


def save_draft(pid, text):
    """Keep what is being typed. Once slides are designed the script they came from stays as it was (a draft is kept beside it); before
    that the script is simply the text."""
    p = _read(pid)
    if p is None: return None
    if p["versions"]: p["draft"] = None if text == p["script"] else text
    else:
        p["script"], p["draft"] = text, None
        (folder(pid) / "script.txt").write_text(text)
    p["updated"] = time.time(); _write(p)
    return p


def chat_load(pid):
    try: items = json.loads((folder(pid) / "chat.json").read_text())
    except (FileNotFoundError, ValueError): return []
    return items if isinstance(items, list) else []


def chat_save(pid, items):
    if _read(pid) is None: return
    (folder(pid) / "chat.json").write_text(json.dumps(items[-60:]))


def set_script(pid, script_text):
    p = _read(pid); p["script"] = script_text; p["draft"] = None; p["updated"] = time.time()
    _write(p); (folder(pid) / "script.txt").write_text(script_text)
    return p


def save_version(pid, html, slides, note, cost=0.0, issues=(), script_text=None, mode="design", at=None, label=None):
    """Store a new version and make it current. `slides` is the per-slide design (None for the basic layout)."""
    p = _read(pid); n = (p["versions"][-1]["n"] + 1) if p["versions"] else 1
    f = folder(pid); (f / "versions").mkdir(exist_ok=True)
    (f / "versions" / f"v{n}.html").write_text(html, encoding="utf-8")
    (f / "versions" / f"v{n}.json").write_text(json.dumps({"slides": slides, "script": script_text if script_text is not None else p["script"]}))
    (f / "module.html").write_text(html, encoding="utf-8")
    p["versions"].append({"n": n, "at": at or time.time(), "note": note, "cost": round(cost, 3), "mode": mode,
                          "issues": [i if isinstance(i, dict) else i.to_dict() for i in issues], **({"label": label} if label else {})})
    p["current"] = n; p["updated"] = time.time()
    if script_text is not None: p["script"] = script_text; p["draft"] = None; (f / "script.txt").write_text(script_text)
    _write(p)
    return p


def set_current(pid, n):
    """Make version n the one the project shows (and the video is made from), without adding a version."""
    p = _read(pid); html = version_html(pid, n)
    if html is None: raise ValueError("That version doesn't exist.")
    (folder(pid) / "module.html").write_text(html, encoding="utf-8")
    p["current"] = int(n); _write(p)
    return p


def add_feedback(pid, text, scope):
    p = _read(pid); p["feedback"].append({"at": time.time(), "text": text, "scope": scope}); _write(p)


def slides(pid, n=None):
    """The per-slide designs of a version (the current one by default)."""
    p = _read(pid); n = n or p["current"]
    try: return json.loads((folder(pid) / "versions" / f"v{n}.json").read_text()).get("slides") or {}
    except (FileNotFoundError, ValueError): return {}


def kind_of(note):
    """Where a version came from, read from its note: restore, import, assistant, script, quick or design."""
    n = (note or "").lower()
    for start, kind in (("restored", "restore"), ("imported", "import"), ("assistant", "assistant"), ("script edited", "script"), ("quick layout", "quick")):
        if n.startswith(start): return kind
    return "design"


def set_label(pid, n, label):
    """Give a version a name of your own (empty clears it)."""
    p = _read(pid); label = re.sub(r"\s+", " ", str(label or "")).strip()
    if len(label) > 60: raise ValueError("Keep the name to 60 characters or fewer.")
    v = next((v for v in p["versions"] if v["n"] == int(n)), None)
    if v is None: raise ValueError("That version doesn't exist.")
    if label: v["label"] = label
    else: v.pop("label", None)
    _write(p); return p


def version_script(pid, n):
    """The script a version was made from (None if it isn't there)."""
    try: return json.loads((folder(pid) / "versions" / f"v{int(n)}.json").read_text()).get("script")
    except (FileNotFoundError, ValueError): return None


def version_html(pid, n):
    try: return (folder(pid) / "versions" / f"v{int(n)}.html").read_text(encoding="utf-8")
    except FileNotFoundError: return None


def restore(pid, n):
    """Make an earlier version current again (its script too), as a new version so nothing is lost."""
    p = _read(pid)
    html = version_html(pid, n)
    if html is None: raise ValueError("That version doesn't exist.")
    data = json.loads((folder(pid) / "versions" / f"v{int(n)}.json").read_text())
    return save_version(pid, html, data.get("slides"), f"Restored version {n}", script_text=data.get("script", p["script"]))


def delete(pid):
    shutil.rmtree(folder(pid), ignore_errors=True)
