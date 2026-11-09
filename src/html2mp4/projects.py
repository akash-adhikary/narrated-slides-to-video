"""Modules on disk: a script, its designed HTML, and every version along the way.

    ~/Downloads/Narrated Videos/Modules/<name>/
        project.json     title, script, feedback history, versions
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
    try: return json.loads((folder(pid) / "project.json").read_text())
    except (FileNotFoundError, ValueError): return None


def _write(p):
    f = folder(p["id"]); f.mkdir(parents=True, exist_ok=True)
    (f / "project.json").write_text(json.dumps(p, indent=1))


def create(title, script_text, batch=""):
    """Start a project; the id is the folder name, made unique."""
    base, pid, n = slugify(title), slugify(title), 2
    while folder(pid).exists(): pid, n = f"{base}-{n}", n + 1
    p = {"id": pid, "title": title, "script": script_text, "created": time.time(), "updated": time.time(), "current": 0,
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
                out.append({k: p[k] for k in ("id", "title", "created", "updated", "current", "batch") if k in p}
                           | {"versions": len(p["versions"]), "designed": bool(p["versions"])})
    return sorted(out, key=lambda x: -x["updated"])


def set_script(pid, script_text):
    p = _read(pid); p["script"] = script_text; p["updated"] = time.time()
    _write(p); (folder(pid) / "script.txt").write_text(script_text)
    return p


def save_version(pid, html, slides, note, cost=0.0, issues=(), script_text=None, mode="design"):
    """Store a new version and make it current. `slides` is the per-slide design (None for the basic layout)."""
    p = _read(pid); n = (p["versions"][-1]["n"] + 1) if p["versions"] else 1
    f = folder(pid); (f / "versions").mkdir(exist_ok=True)
    (f / "versions" / f"v{n}.html").write_text(html, encoding="utf-8")
    (f / "versions" / f"v{n}.json").write_text(json.dumps({"slides": slides, "script": script_text if script_text is not None else p["script"]}))
    (f / "module.html").write_text(html, encoding="utf-8")
    p["versions"].append({"n": n, "at": time.time(), "note": note, "cost": round(cost, 3), "mode": mode,
                          "issues": [i if isinstance(i, dict) else i.to_dict() for i in issues]})
    p["current"] = n; p["updated"] = time.time()
    if script_text is not None: p["script"] = script_text; (f / "script.txt").write_text(script_text)
    _write(p)
    return p


def add_feedback(pid, text, scope):
    p = _read(pid); p["feedback"].append({"at": time.time(), "text": text, "scope": scope}); _write(p)


def slides(pid, n=None):
    """The per-slide designs of a version (the current one by default)."""
    p = _read(pid); n = n or p["current"]
    try: return json.loads((folder(pid) / "versions" / f"v{n}.json").read_text()).get("slides") or {}
    except (FileNotFoundError, ValueError): return {}


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
