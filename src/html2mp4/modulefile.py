"""The module file: everything about one module (script, slide designs, finished page, history) in one readable file.

Written as JSON (`.h2m.json`), or as the same data in YAML (`.h2m.yaml`) for reading and hand edits; either opens in the Studio.

    format, schema      what this is, and which version of the layout (older files are brought forward when opened)
    name                the label the module has in the Studio (lists, URL, file names), with its number if it has one
    title, script       the video's own title (from the script) and the script, exactly as written
    brand               the look it was made with (colours and fonts; a reference, never applied on import)
    pronunciations      the spoken forms the script uses
    current             the version number the file opens on
    versions            [{n, at, note, label?, mode, script, slides, html}]; one for a plain export, all of them with history
    integrity           a checksum of the above, so a hand edit is noticed (it is never refused for it)
"""
import hashlib, json, re, time

import yaml

from html2mp4 import __version__, config, projects, script as script_parser

FORMAT, SCHEMA = "html2mp4.module", 2
BRAND_KEYS = ("style", "background", "text", "accent", "accent2", "heading_font", "body_font", "footer_text")


class ModuleFileError(ValueError):
    """The file isn't a module file, or is one this version can't read. The message is meant for the person who opened it."""


def checksum(doc):
    body = {k: v for k, v in doc.items() if k != "integrity"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _spoken(script_text, pronunciations):
    low = script_text.lower()
    return {w: s for w, s in pronunciations.items() if w.lower() in low}


def build(pid, version=None, history=False):
    """The module file for a project, as a dict. `version` picks the one to open on (the current one by default);
    `history` includes every version instead of just that one."""
    p = projects.get(pid)
    if not p: raise ModuleFileError("That module doesn't exist.")
    cur = version or p["current"]
    wanted = [v for v in p["versions"] if history or v["n"] == cur]
    if not wanted and p["versions"]: raise ModuleFileError("That version doesn't exist.")
    versions = []
    for v in wanted:
        n = v["n"]
        try: data = json.loads((projects.folder(pid) / "versions" / f"v{n}.json").read_text())
        except (FileNotFoundError, ValueError): data = {}
        versions.append({"n": n, "at": v["at"], "note": v.get("note", ""), "mode": v.get("mode", "design"), **({"label": v["label"]} if v.get("label") else {}),
                         "script": data.get("script", p["script"]), "slides": data.get("slides"), "html": projects.version_html(pid, n)})
    script_text = next((v["script"] for v in versions if v["n"] == cur), projects.working_script(p))
    try: title = script_parser.parse(script_text).title
    except script_parser.ScriptError: title = p["title"]
    brand = config.brand()
    doc = {"format": FORMAT, "schema": SCHEMA, "generator": f"html2mp4 {__version__}",
           "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "name": p["name"], "title": title, "script": script_text,
           "brand": {k: brand[k] for k in BRAND_KEYS if k in brand},
           "pronunciations": _spoken(script_text, config.glossary()["pronunciations"]),
           "current": cur if versions else 0, "versions": versions}
    doc["integrity"] = {"sha256": checksum(doc)}
    return doc


class _Dumper(yaml.SafeDumper):
    pass


def _text(dumper, s):
    """Multi-line text (the script, the HTML) as readable blocks instead of one escaped line."""
    return dumper.represent_scalar("tag:yaml.org,2002:str", s, style="|" if "\n" in s else None)


_Dumper.add_representer(str, _text)


def dumps(doc, fmt="json"):
    if fmt == "yaml": return yaml.dump(doc, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=10_000)
    return json.dumps(doc, ensure_ascii=False, indent=1)


def sniff(text):
    """Whether text looks like a module file (JSON or YAML) rather than an HTML page."""
    head = text.lstrip()[:400]
    return FORMAT in head and not head.lower().startswith(("<!doctype", "<html"))


def loads(text):
    """Read and check a module file (JSON or YAML). Returns {"doc", "edited"}: `edited` is True when the checksum doesn't match,
    which is normal after a hand edit and only worth a mention."""
    try: doc = json.loads(text)
    except ValueError:
        try: doc = yaml.safe_load(text)
        except yaml.YAMLError as e: raise ModuleFileError(f"This file couldn't be read as JSON or YAML ({str(e).splitlines()[0]}).")
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise ModuleFileError("This isn't a module file made by the Studio.")
    sha = (doc.get("integrity") or {}).get("sha256"); edited = sha != checksum(doc)      # judged on the file as written, before it is brought forward
    doc = migrate(doc)
    if not isinstance(doc.get("script"), str) or not doc["script"].strip(): raise ModuleFileError("This module file has no script.")
    versions = doc.get("versions") or []
    if not isinstance(versions, list) or any(not isinstance(v, dict) or not isinstance(v.get("n"), int) for v in versions):
        raise ModuleFileError("The versions in this file are malformed.")
    if versions and doc.get("current") not in [v["n"] for v in versions]: raise ModuleFileError("This file points at a version it doesn't contain.")
    return {"doc": doc, "edited": edited}


def migrate(doc):
    """Bring a file written by an older layout up to the current one, and refuse one from the future."""
    schema = doc.get("schema")
    if not isinstance(schema, int) or schema < 1: raise ModuleFileError("This module file has no valid version number.")
    if schema > SCHEMA: raise ModuleFileError(f"This file was made by a newer Studio (layout {schema}). Update the Studio to open it.")
    if schema < 2:                                    # layout 1 had no module name: it was the title
        doc = {**doc, "schema": 2, "name": doc.get("name") or doc.get("title") or "Module"}
    return doc


def filename(name, fmt):
    return (re.sub(r"[^\w\-· ]+", "", name).strip() or "module") + (".h2m.yaml" if fmt == "yaml" else ".h2m.json")
