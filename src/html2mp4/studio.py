"""html2mp4 Studio — a local web app for turning narrated HTML modules into videos.

usage: html2mp4-studio            # opens http://127.0.0.1:8765 in your browser
Videos are saved to ~/Downloads/Narrated Videos (override with HTML2MP4_OUTPUT).
"""
import dataclasses, json, os, pathlib, queue, re, shutil, socket, subprocess, sys, threading, time, uuid, webbrowser

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from html2mp4 import chat, ai, brandkit, cli, compose, config, design, modulefile, music as music_beds, projects, review, script, verify

HOME = cli.CACHE / "studio"
UPLOADS, PREVIEWS = HOME / "uploads", HOME / "previews"
JOBS_FILE = HOME / "jobs.json"
OUTPUT = pathlib.Path(os.environ.get("HTML2MP4_OUTPUT", pathlib.Path.home() / "Downloads" / "Narrated Videos"))
WEB = pathlib.Path(__file__).with_name("web")
SAMPLE_TEXT = "Hi there. I'll be narrating your module, clearly and at a comfortable pace."
MUSIC_INFO = {
    "gentle-pulse": ("Gentle pulse", "Soft chords with a light, steady rhythm"),
    "calm-pad":     ("Calm pad", "Warm, ambient and unobtrusive"),
    "warm-keys":    ("Warm keys", "Mellow electric piano"),
}

app = FastAPI(title="html2mp4 Studio", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.middleware("http")
async def revalidate_static(request, call_next):
    """Browsers must check for a newer page and scripts, so an update (git pull) shows up on the next reload."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response
jobs: dict[str, dict] = {}
# two lanes so a quick preview never waits behind a full video; each lane does one job at a time
queues: dict[str, "queue.Queue[str]"] = {"video": queue.Queue(), "preview": queue.Queue()}
cancels: dict[str, threading.Event] = {}
PREVIEW_SECONDS = 10
ACTIVE = ("queued", "running", "cancelling")


# ---------------------------------------------------------------- helpers

def save_jobs():
    HOME.mkdir(parents=True, exist_ok=True)
    keep = {k: j for k, j in jobs.items() if j.get("kind") != "preview"}      # previews are throwaway
    JOBS_FILE.write_text(json.dumps(keep, indent=1, default=str))


def load_jobs():
    if JOBS_FILE.exists():
        for j in json.loads(JOBS_FILE.read_text()).values():
            if j["status"] in ACTIVE:                         # interrupted by a restart
                j.update(status="failed", error="The studio was closed before this video finished.")
            jobs[j["id"]] = j


def unique_path(folder, stem, ext):
    stem = re.sub(r"\s*:\s*", " - ", stem)                          # "Module 4: Intro" -> "Module 4 - Intro"
    stem = re.sub(r'[\\/*?"<>|]+', "-", stem).strip(" .-")[:90] or "video"
    p, n = folder / f"{stem}{ext}", 2
    while p.exists(): p, n = folder / f"{stem} ({n}){ext}", n + 1
    return p


def to_m4a(src, dst, seconds=None):
    cmd = [cli.FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", src]
    if seconds: cmd += ["-t", seconds, "-af", f"afade=t=in:d=0.5,afade=t=out:st={seconds - 2}:d=2"]
    cli.run(cmd + ["-c:a", "aac", "-b:a", "160k", dst])


def public(job):
    j = {k: v for k, v in job.items() if k not in ("html_path", "music_arg")}
    if job.get("kind") != "preview" and job["status"] == "running" and cli.RENDER_PAUSE.is_set() \
            and job.get("label") == "Animating the slides":
        j["label"] = "Paused for a moment while your preview is made"
        j["eta"] = None
    if job["status"] == "queued":       # say what it's waiting for, so a wait never looks like a hang
        ahead = [o for o in jobs.values() if o.get("kind") == job.get("kind") and o["status"] in ("running", "cancelling")]
        j["waiting_for"] = ahead[0]["title"] if ahead else None
    if job["status"] == "running" and job.get("started"):
        elapsed, p = time.time() - job["started"], job.get("progress", 0)
        # the voice step's speed varies a lot, so trust the measured rate only once animating is under way
        j["eta"] = elapsed * (1 - p) / p if p > 0.3 else max(20, job.get("estimate", 120) - elapsed)
    return j


# ---------------------------------------------------------------- worker

def worker(lane):
    while True:
        jid = queues[lane].get()
        job = jobs.get(jid)
        if not job or job["status"] != "queued": continue          # cancelled (or removed) while waiting
        job.update(status="running", started=time.time(), progress=0.0, label="Getting ready")
        if lane == "preview": cli.RENDER_PAUSE.set()
        def progress(f, label): job.update(progress=round(f, 4), label=label)
        try:
            preview = job.get("kind") == "preview"
            out = PREVIEWS / f"preview-{jid}.mp4" if preview else unique_path(OUTPUT, job["title"], ".mp4")
            res = cli.convert(job["html_path"], out, job["voice"], job["speed"], job["music_arg"],
                              music_volume=job.get("music_volume", "balanced"), quality=job.get("quality", "1440p"),
                              preview_seconds=PREVIEW_SECONDS if preview else None, progress=progress,
                              cancel=cancels.setdefault(jid, threading.Event()),
                              nice=0 if preview else 10, pausable=not preview)   # full videos yield to previews
            job.update(status="done", progress=1.0, label="Done", finished=time.time(),
                       duration=res["duration"], files={k: str(res[k]) for k in ("mp4", "srt", "vtt")})
        except cli.Cancelled:
            job.update(status="cancelled", label="Cancelled", finished=time.time())
        except cli.ConversionError as e:
            job.update(status="failed", error=str(e))
        except Exception as e:  # noqa: BLE001 — surface anything unexpected to the user, keep serving
            job.update(status="failed", error=f"Something went wrong while creating the video ({type(e).__name__}: {e}).")
        cancels.pop(jid, None)
        if lane == "preview" and queues["preview"].empty(): cli.RENDER_PAUSE.clear()
        save_jobs()


def cancel_job(jid):
    job = jobs.get(jid)
    if not job or job["status"] not in ACTIVE: return
    if job["status"] == "queued": job.update(status="cancelled", label="Cancelled")
    else:
        job.update(status="cancelling", label="Stopping")
        cancels.setdefault(jid, threading.Event()).set()


def warm_up():
    """Prepare the music beds and previews in the background so the first click is instant."""
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    for style in music_beds.STYLES:
        dst = PREVIEWS / f"music-{style}.m4a"
        if not dst.exists(): to_m4a(music_beds.ensure(style, cli.CACHE / "music"), dst, seconds=24)
    for voice in cli.VOICES:
        if any(j["status"] in ACTIVE for j in jobs.values()): return   # don't slow a render
        voice_sample(voice, 0.9)


# ---------------------------------------------------------------- API

@app.get("/", response_class=HTMLResponse)
def index(): return (WEB / "index.html").read_text()


@app.get("/api/options")
def options():
    return {"voices": [{"id": k, "name": n, "desc": d} for k, (n, d) in cli.VOICES.items()],
            "music": [{"id": k, "name": n, "desc": d} for k, (n, d) in MUSIC_INFO.items()],
            "preview_seconds": PREVIEW_SECONDS,
            "output": str(OUTPUT)}


def register_upload(filename, data):
    """Stage a module for the Create video page and describe it."""
    uid = uuid.uuid4().hex[:12]
    folder = UPLOADS / uid; folder.mkdir(parents=True)
    path = folder / re.sub(r"[^\w.\- ]+", "_", filename)
    path.write_bytes(data)
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        scenes = cli.load_scenes(text)
    except cli.ConversionError as e:
        shutil.rmtree(folder); raise HTTPException(422, str(e))
    words = sum(len(c.split()) for s in scenes for c in s["chunks"])
    sentences = sum(len(s["chunks"]) for s in scenes)
    return {"upload_id": uid, "filename": filename, "title": cli.page_title(text, path.stem),
            "scenes": scenes, "sentences": sentences, "words": words}


@app.post("/api/inspect")
async def inspect(file: UploadFile = File(...)):
    if not re.search(r"\.html?$", file.filename or "", re.I):
        raise HTTPException(400, "Please choose an .html file.")
    return register_upload(file.filename, await file.read())


@app.post("/api/music-upload")
async def music_upload(file: UploadFile = File(...)):
    ext = pathlib.Path(file.filename or "").suffix.lower()
    if ext not in (".mp3", ".m4a", ".wav", ".aac", ".flac", ".ogg", ".aiff", ".aif"):
        raise HTTPException(400, "Please choose an audio file (MP3, M4A, WAV, AAC, FLAC or OGG).")
    uid = uuid.uuid4().hex[:12]
    folder = UPLOADS / "music"; folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{uid}{ext}").write_bytes(await file.read())
    return {"music_id": f"upload:{uid}{ext}", "name": file.filename}


@app.get("/api/voice-sample/{voice}")
def voice_sample(voice: str, speed: float = 0.9):
    if voice not in cli.VOICES: raise HTTPException(404)
    dst = PREVIEWS / f"voice-{voice}-{speed}.m4a"
    if not dst.exists():
        [[a]] = cli.synthesize([{"chunks": [SAMPLE_TEXT]}], voice, speed, cli.CACHE / "tts")
        import soundfile as sf
        tmp = PREVIEWS / f"voice-{voice}-{speed}-{threading.get_ident()}.wav"; PREVIEWS.mkdir(parents=True, exist_ok=True)
        sf.write(tmp, a, cli.TTS_SR); to_m4a(tmp, dst); tmp.unlink()
    return FileResponse(dst, media_type="audio/mp4")


@app.get("/api/music-preview/{style}")
def music_preview(style: str):
    if style not in music_beds.STYLES: raise HTTPException(404)
    dst = PREVIEWS / f"music-{style}.m4a"
    if not dst.exists(): to_m4a(music_beds.ensure(style, cli.CACHE / "music"), dst, seconds=24)
    return FileResponse(dst, media_type="audio/mp4")


class JobRequest(BaseModel):
    upload_id: str
    voice: str = "af_heart"
    speed: float = 0.9
    music: str = "gentle-pulse"
    music_volume: str = "balanced"
    quality: str = "1440p"


@app.post("/api/preview")
def create_preview(req: JobRequest): return create_job(req, kind="preview")


@app.post("/api/jobs")
def create_job(req: JobRequest, kind: str = "video"):
    folder = UPLOADS / re.sub(r"\W", "", req.upload_id)
    htmls = list(folder.glob("*.htm*"))
    if not htmls: raise HTTPException(404, "That upload has expired — please choose the file again.")
    if req.voice not in cli.VOICES: raise HTTPException(400, "Unknown voice.")
    if req.music_volume not in cli.MUSIC_VOLUMES or req.quality not in cli.QUALITIES:
        raise HTTPException(400, "Unknown music volume or quality.")
    if req.music.startswith("upload:"):
        music_arg = str(UPLOADS / "music" / pathlib.Path(req.music[7:]).name)
    elif req.music in music_beds.STYLES or req.music == "none":
        music_arg = req.music
    else: raise HTTPException(400, "Unknown music choice.")
    text = htmls[0].read_text(encoding="utf-8", errors="replace")
    words = sum(len(c.split()) for s in cli.load_scenes(text) for c in s["chunks"])
    jid = uuid.uuid4().hex[:10]
    seconds = words / (2.4 * req.speed)                     # rough video length
    work = PREVIEW_SECONDS * 2.2 + 15 if kind == "preview" else 40 + seconds * (1.4 if req.quality == "1080p" else 2.2)
    jobs[jid] = {"id": jid, "kind": kind, "title": cli.page_title(text, htmls[0].stem), "filename": htmls[0].name,
                 "voice": req.voice, "speed": req.speed, "music": req.music, "music_arg": music_arg,
                 "music_volume": req.music_volume, "quality": req.quality,
                 "html_path": str(htmls[0]), "status": "queued", "progress": 0.0, "label": "Waiting to start",
                 "created": time.time(), "estimate": work}
    if kind == "preview":       # a new preview replaces any older one that's still waiting or running
        for other in list(jobs.values()):
            if other.get("kind") == "preview" and other["id"] != jid: cancel_job(other["id"])
    save_jobs(); queues[kind].put(jid)
    return public(jobs[jid])


@app.get("/api/jobs")
def list_jobs(): return sorted((public(j) for j in jobs.values() if j.get("kind") != "preview"), key=lambda j: -j["created"])


@app.get("/api/active")
def active_jobs():
    """Everything queued or running, previews included, oldest first, so a reloaded page can reconnect."""
    return sorted((public(j) for j in jobs.values() if j["status"] in ACTIVE), key=lambda j: j["created"])


@app.post("/api/jobs/{jid}/cancel")
def cancel(jid: str):
    if jid not in jobs: raise HTTPException(404)
    cancel_job(jid); save_jobs()
    return public(jobs[jid])


@app.get("/api/jobs/{jid}")
def get_job(jid: str):
    if jid not in jobs: raise HTTPException(404)
    return public(jobs[jid])


@app.delete("/api/jobs/{jid}")
def forget_job(jid: str):
    if jid in jobs and jobs[jid]["status"] not in ACTIVE:
        del jobs[jid]; save_jobs()
    return {"ok": True}


@app.get("/api/jobs/{jid}/file/{kind}")
def job_file(jid: str, kind: str, download: bool = False):
    job = jobs.get(jid)
    if not job or job["status"] != "done" or kind not in ("mp4", "srt", "vtt"): raise HTTPException(404)
    p = pathlib.Path(job["files"][kind])
    if not p.exists(): raise HTTPException(410, "This file has been moved or deleted.")
    types = {"mp4": "video/mp4", "srt": "application/x-subrip", "vtt": "text/vtt"}
    return FileResponse(p, media_type=types[kind], filename=p.name if download else None)


@app.post("/api/jobs/{jid}/reveal")
def reveal(jid: str):
    job = jobs.get(jid)
    if not job or job["status"] != "done": raise HTTPException(404)
    p = job["files"]["mp4"]
    if sys.platform == "darwin": subprocess.run(["open", "-R", p])
    elif sys.platform == "win32": subprocess.run(["explorer", "/select,", p])
    else: subprocess.run(["xdg-open", str(pathlib.Path(p).parent)])
    return {"ok": True}


# ---------------------------------------------------------------- settings

BRAND_PREVIEW = script.parse("""Title: Your Module Title
Subtitle: Programme name · Module 1
Say: This is how a title slide looks.

## How content slides look
Show: Clear headings · Your colours and fonts · Your logo and footer
Say: Content slides use your colours and fonts.
Say: Points appear one by one as the narrator speaks.
""")


def anthropic_client(key=None):
    import anthropic
    return anthropic.Anthropic(api_key=key or config.api_key(), max_retries=1, timeout=20)


def verify_key(key=None):
    """Make one free metadata call to check the key works; raise HTTPException with a plain message if not."""
    import anthropic
    try:
        anthropic_client(key).models.retrieve(config.DESIGN_MODEL)
    except anthropic.AuthenticationError:
        raise HTTPException(400, "Anthropic didn't accept that key. Check it was copied completely.")
    except anthropic.PermissionDeniedError:
        raise HTTPException(400, "That key doesn't have access to the model used for designing slides.")
    except anthropic.APIConnectionError:
        raise HTTPException(503, "Couldn't reach Anthropic. Check your internet connection.")
    except anthropic.APIStatusError as e:
        raise HTTPException(502, f"Anthropic returned an error ({e.status_code}). Try again in a moment.")
    except TypeError:          # no credentials anywhere: the SDK can't build a request
        raise HTTPException(400, "No API key is set. Paste one in Settings.")


@app.get("/api/settings")
def get_settings():
    return {"api_key": config.api_key_status(), "brand": config.brand(), "fonts": config.available_fonts(),
            "design_quality": config.design_quality(), "motion": config.motion()}


@app.put("/api/settings/motion")
def put_motion(body: dict):
    try: config.set_motion(body.get("value", ""))
    except ValueError as e: raise HTTPException(400, str(e))
    return {"motion": config.motion()}


@app.put("/api/settings/design-quality")
def put_design_quality(body: dict):
    try: config.set_design_quality(body.get("value", ""))
    except ValueError as e: raise HTTPException(400, str(e))
    return {"design_quality": config.design_quality()}


class KeyIn(BaseModel):
    key: str


@app.put("/api/settings/api-key")
def put_api_key(body: KeyIn):
    key = body.key.strip()
    if not key.startswith("sk-ant-"): raise HTTPException(400, "That doesn't look like an Anthropic key. Keys start with sk-ant-.")
    verify_key(key)
    config.set_api_key(key)
    return config.api_key_status()


@app.post("/api/settings/api-key/test")
def test_api_key():
    if not config.api_key_status()["set"]: raise HTTPException(400, "No API key is set yet. Paste one above.")
    verify_key()
    return {"ok": True}


@app.delete("/api/settings/api-key")
def delete_api_key():
    config.clear_api_key()
    return config.api_key_status()


@app.put("/api/settings/brand")
def put_brand(changes: dict):
    try: return config.update_brand(changes)
    except ValueError as e: raise HTTPException(400, str(e))


@app.post("/api/settings/brand/reset")
def reset_brand(): return config.reset_brand()


@app.post("/api/settings/logo")
async def post_logo(file: UploadFile = File(...), slot: str = "logo_on_dark"):
    if slot not in ("logo_on_dark", "logo_on_light"): raise HTTPException(400, "Unknown logo slot.")
    types = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml", ".webp": "image/webp"}
    mime = types.get(pathlib.Path(file.filename or "").suffix.lower())
    if not mime: raise HTTPException(400, "Please choose a PNG, JPG, SVG or WebP image.")
    data = await file.read()
    if len(data) > config.LOGO_MAX_BYTES: raise HTTPException(400, "That image is larger than 512 KB. Try a smaller or compressed version.")
    import base64
    config.set_logo(f"data:{mime};base64,{base64.b64encode(data).decode()}", slot)
    return config.brand()


@app.delete("/api/settings/logo")
def delete_logo(slot: str = "logo_on_dark"):
    if slot not in ("logo_on_dark", "logo_on_light"): raise HTTPException(400, "Unknown logo slot.")
    config.set_logo("", slot)
    if not config.brand().get("logo_on_dark") and not config.brand().get("logo_on_light"): config.set_logo("", "logo")
    return config.brand()


@app.post("/api/brandkit/analyze")
async def brandkit_analyze(files: list[UploadFile] = File(...)):
    """Read a dropped brand kit (folder, zip, PDF, logos, fonts, module) and propose a brand to review."""
    from starlette.concurrency import run_in_threadpool
    items = [(f.filename or "file", await f.read()) for f in files]
    if sum(len(d) for _, d in items) > 200 * 1024 * 1024: raise HTTPException(400, "That's more than 200 MB. Drop just the brand files.")
    try:
        p = await run_in_threadpool(brandkit.analyze, items)
    except Exception as e:  # noqa: BLE001 — a malformed file shouldn't take the Studio down
        raise HTTPException(400, f"Couldn't read those files ({type(e).__name__}: {e}).")
    if not (p["palette"] or p["logos"] or p["fonts"]):
        raise HTTPException(400, "Nothing usable was found. Drop a brand guidelines PDF, logos, font files, or a module (.html).")
    return p


class KitApply(BaseModel):
    id: str
    choices: dict = {}


@app.post("/api/brandkit/apply")
def brandkit_apply(body: KitApply):
    try: return brandkit.apply(body.id, body.choices)
    except ValueError as e: raise HTTPException(400, str(e))


@app.post("/api/brandkit/remove")
def brandkit_remove(): return brandkit.remove_kit()


@app.get("/api/settings/brand-preview", response_class=HTMLResponse)
def brand_preview(): return compose.basic_module(BRAND_PREVIEW, config.brand())


# ---------------------------------------------------------------- write: script -> module

design_jobs: dict[str, dict] = {}
design_lock = threading.Lock()            # one design at a time: each uses the machine and the API heavily


def outline(m):
    return {"title": m.title, "subtitle": m.subtitle, "sentences": m.sentences, "words": m.words,
            "seconds": round(m.words / 2.2 + m.sentences * 0.45 + len(m.slides) * 0.9 + 2.2),
            "intro": m.intro, "slides": [dataclasses.asdict(x) | {"id": f"s{i + 1}"} for i, x in enumerate(m.slides)]}


def parse_or_422(text, title=None, subtitle=None):
    try: return script.parse(text, title or None, subtitle or None)
    except script.ScriptError as e: raise HTTPException(422, str(e))


class ScriptIn(BaseModel):
    script: str
    title: str = ""
    subtitle: str = ""


@app.post("/api/write/parse")
def write_parse(body: ScriptIn): return outline(parse_or_422(body.script, body.title, body.subtitle))


@app.get("/api/write/example")
def write_example(): return {"script": script.EXAMPLE}


@app.post("/api/write/review")
async def write_review(body: ScriptIn):
    from starlette.concurrency import run_in_threadpool
    parse_or_422(body.script, body.title, body.subtitle)
    if not config.api_key_status()["set"]: raise HTTPException(400, "Checking your script needs an Anthropic API key. Add one in Settings.")
    try: found, cost = await run_in_threadpool(review.review, body.script)
    except ai.AIError as e: raise HTTPException(400, str(e))
    return {"suggestions": found, "cost": round(cost, 3)}


# ---------------------------------------------------------------- write: talk to Claude to build the script

chat_jobs: dict[str, dict] = {}


class ChatIn(BaseModel):
    messages: list[dict]
    script: str = ""
    project_id: str | None = None


def run_chat(job, body, designed, slides, module=None):
    try:
        res = chat.turn(body.messages, body.script, designed, slides, on_reply=lambda t: job.update(reply=t), module=module)
        job.update(status="done", result=res, reply=res["reply"])
    except ai.AIError as e:
        job.update(status="failed", error=str(e))
    except Exception as e:  # noqa: BLE001 — surface anything unexpected, keep the Studio running
        job.update(status="failed", error=f"Something went wrong ({type(e).__name__}: {e}).")


@app.post("/api/write/chat")
def write_chat(body: ChatIn):
    """Start one assistant turn in the background; poll /api/write/chat/{id} for the reply as it streams in."""
    if not config.api_key_status()["set"]: raise HTTPException(400, "The assistant needs an Anthropic API key. Add one in Settings.")
    if not body.messages or body.messages[-1].get("role") != "user" or not str(body.messages[-1].get("content", "")).strip():
        raise HTTPException(400, "Write a message first.")
    p = projects.get(body.project_id) if body.project_id else None
    designed = bool(p and p["versions"])
    slides = {k: {"layout": v.get("layout", "")} for k, v in projects.slides(p["id"]).items()} if designed else {}
    for k in [k for k, j in chat_jobs.items() if time.time() - j["created"] > 3600]: chat_jobs.pop(k, None)
    jid = uuid.uuid4().hex[:10]
    job = chat_jobs[jid] = {"id": jid, "status": "running", "reply": "", "created": time.time()}
    module = {"name": p["name"], "version": p["current"] or None} if p else None
    threading.Thread(target=run_chat, args=(job, body, designed, slides, module), daemon=True).start()
    return {"id": jid}


@app.get("/api/write/chat/{jid}")
def write_chat_job(jid: str):
    if jid not in chat_jobs: raise HTTPException(404, "That reply is no longer available.")
    return {k: v for k, v in chat_jobs[jid].items() if k != "created"}


def moment_note(m):
    """Approximate start times, so feedback like "at 2:51" can be matched to a slide."""
    t, rows = 0.6, []
    for i, sl in enumerate(m.slides):
        rows.append(f"s{i + 1} ({sl.title}) starts at about {int(t // 60)}:{int(t % 60):02d}")
        t += sum(len(x.split()) / 2.2 + 0.45 for x in sl.say) + 0.9
    return "Times in the feedback (like 2:51) refer to the finished video. Approximate slide start times: " + "; ".join(rows) + "."


def history_note(p, only, current_feedback):
    """Earlier requests that still apply to these slides, so a new change doesn't quietly undo them."""
    entries = [f for f in p.get("feedback", []) if f["text"] != current_feedback]
    keep = [f for f in entries if f["scope"] in ("all", [], None) or (isinstance(f["scope"], list) and (not only or any(x in only for x in f["scope"])))]
    if not keep: return ""
    return ("Earlier changes the author asked for. Keep them in effect unless the new feedback says otherwise:\n"
            + "\n".join(f"- {f['text']}" + (f" (slides {', '.join(f['scope'])})" if isinstance(f["scope"], list) and f["scope"] else "") for f in keep[-8:]))


def phase_of(label):
    """Which stage of a design a progress label belongs to: plan, write, check, fix or review."""
    for key, phase in (("Checking", "check"), ("Fixing", "fix"), ("Reviewing", "review"), ("Applying", "plan"), ("planning", "plan"),
                       ("written", "write"), ("Designing", "write"), ("Done", "done")):
        if key in label: return phase
    return "plan"


def eta_for(job):
    """A rough time left, from the stage a design is in (nothing can be measured while Claude is planning, so no number is guessed)."""
    phase, label = job.get("phase", "plan"), job.get("label", "")
    m = re.search(r"\((\d+) of (\d+)", label)
    left = (int(m.group(2)) - int(m.group(1))) if m else 0
    return {"plan": None, "write": left * 12 + 90, "check": 75, "fix": 60, "review": 30}.get(phase)


def run_design(job, project_id, only=None, feedback="", note="", mode="design", remap=None):
    """Design, revise or just re-check slides in the background, then save the result as a new version."""
    def progress(f, label): job.update(progress=round(f, 3), label=label, phase=phase_of(label))
    def activity(kind, text): job["activity"].append({"t": round(time.time() - job["started"], 1), "kind": kind, "text": text})
    def thought(key, label, text):
        if text: job["thoughts"][key] = {"label": label, "text": text, "at": time.time()}
        else: job["thoughts"].pop(key, None)
    with design_lock:
        job.update(status="running", started=time.time(), label="Getting ready")
        try:
            p = projects.get(project_id)
            m = script.parse(p["script"])
            brand = config.brand()
            ref = brandkit.reference_file().read_text() if brandkit.reference_file().exists() else None
            prev = projects.slides(project_id) if p["versions"] else {}
            if remap is not None: prev = {new: remap_design(prev[old], old, new) for new, old in remap.items() if old in prev}   # reuse designs after slides moved
            if mode == "basic":
                page = compose.basic_module(m, brand, motion=config.motion(), script_text=p["script"])
                job.update(progress=0.3, label="Checking every slide, step by step")
                found = verify.inspect(page, m, config.glossary()["banned"], shots=False)["issues"]
                projects.save_version(project_id, page, None, note or "Quick layout", issues=found, mode="basic")
                job.update(status="done", progress=1.0, label="Done", cost=0)
                return
            res = design.design(m, brand, reference=ref, previous=prev, only=only, feedback=feedback, progress=progress,
                                activity=activity, thought=thought, effort={"design": config.design_effort()},
                                motion=config.motion(), script_text=p["script"],
                                timing_note=(moment_note(m) + "\n" + history_note(p, only, feedback)).strip() if feedback else "")
            problems = [i for i in res["issues"] if i.kind != "invented"] + [i for i in res["issues"] if i.kind == "invented"]
            projects.save_version(project_id, res["html"], res["slides"], note, cost=res["cost"], issues=problems)
            job.update(status="done", progress=1.0, label="Done", cost=round(res["cost"], 2))
        except (ai.AIError, script.ScriptError) as e:
            job.update(status="failed", error=str(e))
        except Exception as e:  # noqa: BLE001 — surface anything unexpected, keep the Studio running
            job.update(status="failed", error=f"Something went wrong while designing the slides ({type(e).__name__}: {e}).")


def start_design(project_id, **kw):
    jid = uuid.uuid4().hex[:10]
    job = design_jobs[jid] = {"id": jid, "project": project_id, "status": "queued", "progress": 0.0, "label": "Waiting to start", "created": time.time(),
                              "phase": "plan", "activity": [], "thoughts": {}}
    threading.Thread(target=run_design, args=(job, project_id), kwargs=kw, daemon=True).start()
    return job


class GenerateIn(ScriptIn):
    mode: str = "design"


@app.post("/api/write/generate")
def write_generate(body: GenerateIn):
    m = parse_or_422(body.script, body.title, body.subtitle)
    if body.mode == "design" and not config.api_key_status()["set"]:
        raise HTTPException(400, "Designing slides needs an Anthropic API key. Add one in Settings, or choose the quick layout.")
    p = projects.create(m.title, body.script)
    job = start_design(p["id"], note="First design" if body.mode == "design" else "Quick layout", mode=body.mode)
    return {"job": job, "project": p["id"]}


@app.get("/api/write/jobs/{jid}")
def write_job(jid: str):
    if jid not in design_jobs: raise HTTPException(404)
    job = design_jobs[jid]
    j = dict(job)
    j["activity"] = list(job["activity"])[-80:]                                       # snapshots: calls run side by side and keep adding
    j["thoughts"] = sorted((dict(v) for v in list(job["thoughts"].values())), key=lambda v: v["at"])[-3:]
    if j["status"] == "running": j["eta"] = eta_for(job)
    return j


@app.get("/api/write/active")
def write_active():
    """Designs still running or waiting, so a reloaded page can pick them up again."""
    return [dict(j) for j in design_jobs.values() if j["status"] in ("queued", "running")]


def project_view(pid, version=None):
    """A module as the Write page shows it: the current version, or (`version`) an earlier one, whole: its script, slides and checks."""
    p = projects.get(pid)
    if not p: raise HTTPException(404, "That module wasn't found.")
    if version is not None and version not in [v["n"] for v in p["versions"]]: raise HTTPException(404, "That version doesn't exist.")
    viewing = version is not None and version != p["current"]
    n = version if viewing else p["current"]
    shown = (projects.version_script(pid, n) or p["script"]) if viewing else projects.working_script(p)
    try: m = script.parse(shown); outl, title = outline(m), m.title
    except script.ScriptError: outl, title = None, p["title"]
    cur = next((v for v in p["versions"] if v["n"] == n), None)
    return {**{k: p[k] for k in ("id", "name", "created", "updated", "current", "feedback")}, "title": title, "script": shown,
            "version": n, "viewing": viewing, "has_draft": p.get("draft") is not None,
            "designed_script": p["script"] if p["versions"] else "",
            "versions": [{k: v[k] for k in ("n", "at", "note", "cost", "mode")} | {"label": v.get("label", ""), "kind": projects.kind_of(v.get("note"))} for v in p["versions"]],
            "issues": (cur or {}).get("issues", []), "outline": outl,
            "slides": {k: {"layout": v["layout"], "summary": v["summary"]} for k, v in projects.slides(pid, n).items()}}


@app.get("/api/projects")
def list_projects(): return projects.listing()


class NewModuleIn(BaseModel):
    name: str


@app.post("/api/projects")
def create_project(body: NewModuleIn):
    """Start a module: a name, and a script that begins with the video's title (the name without its number)."""
    try: name = projects.clean_name(body.name)
    except ValueError as e: raise HTTPException(400, str(e))
    if projects.name_taken(name): raise HTTPException(409, f"You already have a module called “{name}”.")
    title = projects.video_title(name)
    p = projects.create(title, f"Title: {title}\n", name=name)
    return project_view(p["id"])


class PatchIn(BaseModel):
    name: str | None = None
    script: str | None = None


@app.patch("/api/projects/{pid}")
def patch_project(pid: str, body: PatchIn):
    """Rename a module (its id and address stay the same) and/or save the script as it is being written."""
    if not projects.get(pid): raise HTTPException(404, "That module wasn't found.")
    if body.name is not None:
        try: projects.rename(pid, body.name)
        except ValueError as e: raise HTTPException(409 if "already have" in str(e) else 400, str(e))
    if body.script is not None:
        if len(body.script) > 400_000: raise HTTPException(413, "That script is too long.")
        projects.save_draft(pid, body.script)
    p = projects.get(pid)
    return {"id": pid, "name": p["name"], "updated": p["updated"]}


@app.get("/api/projects/{pid}/chat")
def get_chat(pid: str):
    if not projects.get(pid): raise HTTPException(404)
    return {"items": projects.chat_load(pid)}


class ChatSaveIn(BaseModel):
    items: list[dict]


@app.put("/api/projects/{pid}/chat")
def put_chat(pid: str, body: ChatSaveIn):
    if not projects.get(pid): raise HTTPException(404)
    projects.chat_save(pid, body.items); return {"ok": True}


@app.get("/api/projects/{pid}")
def get_project(pid: str, v: int | None = None): return project_view(pid, v)


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    projects.delete(pid); return {"ok": True}


@app.get("/api/projects/{pid}/module.html", response_class=HTMLResponse)
def project_module(pid: str, v: int | None = None):
    p = projects.get(pid)
    if not p: raise HTTPException(404)
    page = projects.version_html(pid, v or p["current"])
    if page is None: raise HTTPException(404, "That version doesn't exist.")
    return HTMLResponse(compose.refresh_player(page), headers={"Cache-Control": "no-store"})


def attachment(filename):
    """A Content-Disposition for a file name that may hold characters like "·": a plain fallback plus the UTF-8 form browsers prefer."""
    from urllib.parse import quote
    plain = re.sub(r'[^\x20-\x7e]', "", filename).replace('"', "").strip() or "module"
    return f"attachment; filename=\"{plain}\"; filename*=UTF-8''{quote(filename)}"


@app.get("/api/projects/{pid}/download")
def download_module(pid: str, v: int | None = None):
    """The module as one HTML file to review or share: it plays with the browser's voice, works offline (fonts embedded) and can be
    opened again here as an editable project."""
    p = projects.get(pid)
    if not p: raise HTTPException(404)
    page = projects.version_html(pid, v or p["current"])
    if page is None: raise HTTPException(404, "That version doesn't exist.")
    name = re.sub(r'[^\w\-· ]+', "", p["name"]).strip() or "module"
    return HTMLResponse(compose.embed_fonts(compose.refresh_player(page)), headers={"Content-Disposition": attachment(f"{name}.html"), "Cache-Control": "no-store"})


@app.post("/api/projects/import")
def import_module(file: UploadFile = File(...)):
    """Open a module file made by the Studio (here or on another computer) as an editable project.
    (A plain `def`, so it runs in a worker thread: the checker drives a browser.)"""
    raw = file.file.read()
    if len(raw) > 60 * 1024 * 1024: raise HTTPException(413, "That file is too large.")
    try: page = raw.decode("utf-8")
    except UnicodeDecodeError: raise HTTPException(422, "That doesn't look like a module file.")
    if modulefile.sniff(page): return import_module_file(page)
    data = compose.read_project(page)
    if not data:
        raise HTTPException(422, "This file wasn't made in the Studio, so it can't be opened for editing here. "
                                 "You can still turn it into a video: use Create video.")
    try: m = script.parse(data["script"])
    except script.ScriptError as e: raise HTTPException(422, f"The script inside this file couldn't be read: {e}")
    slides = data.get("slides") if isinstance(data.get("slides"), dict) else None
    p = projects.create(m.title, data["script"], name=m.title)
    found = verify.inspect(page, m, config.glossary()["banned"], shots=False)["issues"]
    note = "Imported from a file" + (" (changed outside the Studio)" if data["edited"] else "")
    projects.save_version(p["id"], page, slides, note, issues=found, mode="design" if slides else "basic")
    added = {}
    for word, said in (data.get("pronunciations") or {}).items():         # only words this computer doesn't have yet; nothing is overwritten
        if isinstance(word, str) and isinstance(said, str) and word not in config.glossary()["pronunciations"]: added[word] = said
    if added: config.set_glossary({"pronunciations": {**config.glossary()["pronunciations"], **added}})
    return {"project": p["id"], "name": p["name"], "title": m.title, "edited": data["edited"], "pronunciations_added": len(added)}


def import_module_file(text):
    """Open a module file (.h2m.json or .h2m.yaml) as a new project, with its versions if it has them."""
    try: got = modulefile.loads(text)
    except modulefile.ModuleFileError as e: raise HTTPException(422, str(e))
    doc = got["doc"]
    versions = sorted((v for v in doc.get("versions") or [] if isinstance(v.get("html"), str)), key=lambda v: v["n"])
    try: m = script.parse(doc["script"]); title = m.title
    except script.ScriptError as e:
        if versions: raise HTTPException(422, f"The script inside this file couldn't be read: {e}")
        m, title = None, str(doc.get("title") or doc.get("name") or "Module")             # a module that is only a name and a title so far
    p = projects.create(title, doc["script"], name=doc.get("name") or title)             # a name you already use gets "(2)" rather than a second copy of it
    for v in versions:
        slides = v.get("slides") if isinstance(v.get("slides"), dict) else None
        is_current = v["n"] == doc.get("current")
        found = verify.inspect(v["html"], m, config.glossary()["banned"], shots=False)["issues"] if is_current else []   # the others are history
        note = (v.get("note") or "Imported from a file") if len(versions) > 1 else "Imported from a file" + (" (changed outside the Studio)" if got["edited"] else "")
        projects.save_version(p["id"], v["html"], slides, note, issues=found, script_text=v.get("script") or doc["script"], label=v.get("label") if isinstance(v.get("label"), str) else None,
                              mode=v.get("mode") if v.get("mode") in ("design", "basic") else ("design" if slides else "basic"),
                              at=v.get("at") if isinstance(v.get("at"), (int, float)) else None)
    if versions:
        saved = projects.get(p["id"])["versions"]
        projects.set_current(p["id"], saved[[v["n"] for v in versions].index(doc["current"])]["n"])
        projects.set_script(p["id"], doc["script"])                      # the file's own script wins: a hand edit there is the person's intent
    added = {}
    for word, said in (doc.get("pronunciations") or {}).items():
        if isinstance(word, str) and isinstance(said, str) and word not in config.glossary()["pronunciations"]: added[word] = said
    if added: config.set_glossary({"pronunciations": {**config.glossary()["pronunciations"], **added}})
    return {"project": p["id"], "name": p["name"], "title": title, "edited": got["edited"], "pronunciations_added": len(added),
            "versions": len(versions), "designed": bool(versions)}


@app.get("/api/projects/{pid}/export")
def export_module(pid: str, format: str = "json", history: bool = False, v: int | None = None, inline: bool = False):
    """The module as one file you can share: script, slide designs, the finished page and (optionally) every version.
    JSON by default; format=yaml gives the same data for reading. `inline` shows it instead of downloading it."""
    if format not in ("json", "yaml"): raise HTTPException(400, "format must be json or yaml")
    try: doc = modulefile.build(pid, version=v, history=history)
    except modulefile.ModuleFileError as e: raise HTTPException(404, str(e))
    body = modulefile.dumps(doc, format)
    head = {"Cache-Control": "no-store"}
    if not inline: head["Content-Disposition"] = attachment(modulefile.filename(doc["name"], format))
    return Response(body, media_type="text/plain; charset=utf-8" if inline else ("application/x-yaml" if format == "yaml" else "application/json"), headers=head)


narrations = {}                       # id -> progress of a voice being made (only while it is being made)
NARRATION_VOICE, NARRATION_SPEED = "af_heart", 0.90


def narration_plan(pid, v):
    """The sentences of a module version and where their voiced clips live. The addresses depend only on the module and the
    glossary, never on a running job, so they stay valid when the Studio is restarted."""
    p = projects.get(pid)
    page = projects.version_html(pid, v or p["current"]) if p else None
    if page is None: raise HTTPException(404, "That module wasn't found.")
    scenes = cli.load_scenes(page)
    pron = config.glossary().get("pronunciations", {})
    cache = cli.CACHE / "tts"
    files = [[cli.clip_path(c, NARRATION_VOICE, NARRATION_SPEED, cache, pron) for c in sc["chunks"]] for sc in scenes]
    return scenes, pron, cache, files


def narration_ready(pid, v, scenes, pron, cache, files):
    if not all(f.exists() and f.with_suffix(".json").exists() for row in files for f in row): return None
    q = f"?v={v}" if v else ""
    return {"status": "done", "progress": 1.0, "label": "Ready", "error": "",
            "urls": [[f"/api/projects/{pid}/narration/audio/{si}/{ci}{q}" for ci in range(len(row))] for si, row in enumerate(files)],
            "times": cli.word_times(scenes, NARRATION_VOICE, NARRATION_SPEED, cache, pron)}


@app.post("/api/projects/{pid}/narration")
def make_narration(pid: str, v: int | None = None):
    """Make sure the module's sentences are voiced with the studio voice, so the review player can play what the video will sound like.
    Already voiced: the answer is immediate ("ready"). Otherwise a job reports honest progress."""
    scenes, pron, cache, files = narration_plan(pid, v)
    ready = narration_ready(pid, v, scenes, pron, cache, files)
    if ready: return {"id": None, "ready": ready}
    jid = uuid.uuid4().hex[:10]
    total = cli.pending(scenes, NARRATION_VOICE, NARRATION_SPEED, cache, pron, timings=True)
    job = narrations[jid] = {"status": "running", "progress": 0.0, "label": "Starting…", "error": "", "done": 0, "total": total}

    def work():
        try:
            def status(what):
                job["label"] = ("Waiting for another voice job to finish (a video may be rendering)…" if what == "waiting"
                                else "Loading the voice…")
            def progress(f):
                done = min(total, int(round(f * total)))
                job.update(progress=round(f, 3), done=done, label=f"Making the voice: sentence {min(total, done + 1)} of {total}")
            cli.synthesize(scenes, NARRATION_VOICE, NARRATION_SPEED, cache, progress=progress, pronounce=pron, timings=True, status=status)
            job.update(narration_ready(pid, v, scenes, pron, cache, files) or {"status": "failed", "error": "The voice files could not be found afterwards."})
        except Exception as e:  # noqa: BLE001
            job.update(status="failed", error=f"The studio voice couldn't be prepared ({type(e).__name__}: {e}).")
    threading.Thread(target=work, daemon=True).start()
    return {"id": jid, "ready": None}


@app.get("/api/narration/{jid}")
def narration_status(jid: str):
    job = narrations.get(jid)
    if not job: raise HTTPException(404, "That voice job is no longer running. Press Studio voice again.")
    return dict(job)


@app.get("/api/projects/{pid}/narration/audio/{si}/{ci}")
def narration_audio(pid: str, si: int, ci: int, v: int | None = None):
    _, _, _, files = narration_plan(pid, v)
    try: path = files[si][ci]
    except IndexError: raise HTTPException(404)
    if not path.exists(): raise HTTPException(404, "That sentence hasn't been voiced yet.")
    return FileResponse(path, media_type="audio/wav", headers={"Cache-Control": "max-age=3600"})


class ReviseIn(BaseModel):
    feedback: str
    scope: list[str] = []


@app.post("/api/projects/{pid}/revise")
def revise(pid: str, body: ReviseIn):
    p = projects.get(pid)
    if not p or not p["versions"]: raise HTTPException(404, "Design the slides first.")
    if not config.api_key_status()["set"]: raise HTTPException(400, "Add your Anthropic API key in Settings first.")
    if not body.feedback.strip(): raise HTTPException(400, "Write what you'd like changed.")
    projects.add_feedback(pid, body.feedback.strip(), body.scope or "all")
    return {"job": start_design(pid, only=body.scope or None, feedback=body.feedback.strip(), note=f"Feedback: {body.feedback.strip()[:70]}")}


def align_slides(old_text, new_text):
    """Match the slides of an edited script to the ones before it by content. Returns (remap, changed): `remap` maps a new slide id to the
    old id whose design can be reused (unchanged slides, and edited ones, which start from their old design), and `changed` lists the new
    ids that need designing. Adding or removing a slide in the middle therefore doesn't redesign the slides after it."""
    import difflib
    old, new = script.parse(old_text), script.parse(new_text)
    key = lambda s: (s.title, tuple(s.say), tuple(s.show), s.screen, s.note)
    remap, changed = {}, []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, [key(x) for x in old.slides], [key(x) for x in new.slides], autojunk=False).get_opcodes():
        if op == "equal":
            for k in range(j2 - j1): remap[f"s{j1 + k + 1}"] = f"s{i1 + k + 1}"
        elif op in ("replace", "insert"):
            for k in range(j2 - j1):
                changed.append(f"s{j1 + k + 1}")
                if op == "replace" and k < i2 - i1: remap[f"s{j1 + k + 1}"] = f"s{i1 + k + 1}"
    if old.intro != new.intro or old.title != new.title or old.subtitle != new.subtitle: changed.insert(0, "s0")
    return remap, changed


def changed_slides(old_text, new_text):
    """Slide ids whose script changed (or are new), so only those are redesigned after an edit."""
    return [i for i in align_slides(old_text, new_text)[1] if i != "s0"]


def edit_note(old_text, new_text, ids, remap=None):
    """What to tell the designer when a script was edited: which slides, and what the narration used to say."""
    if not ids: return ""
    old, new = script.parse(old_text), script.parse(new_text)
    remap = remap if remap is not None else {f"s{i + 1}": f"s{i + 1}" for i in range(min(len(old.slides), len(new.slides)))}
    lines = [f"The script was edited, so update the design of {', '.join(ids)} to match the new narration and on-screen text. "
             "Keep the same look and feel. Keep everything the author's on-screen description still asks for, even if the narration "
             "no longer says it aloud (it can appear with the nearest sentence). Remove only what the edit removed."]
    for sid in ids:
        o = remap.get(sid)
        if o and int(o[1:]) <= len(old.slides): lines.append(f"The previous narration of {sid}:\n" + "\n".join(f"  {k}: {t}" for k, t in enumerate(old.slides[int(o[1:]) - 1].say)))
        else: lines.append(f"{sid} is a new slide: design it to match the other slides.")
    return "\n".join(lines)


def remap_design(design_, old, new):
    """A slide's saved design, moved from slide id `old` to `new`: its CSS selectors (#s3 ...) and the ids it declares and refers to
    (id="s3-glow", url(#s3-glow)) follow it. Class names that merely start with the old id (class="s3-card") are left alone: the CSS
    that styles them still uses them, scoped under the new id."""
    if old == new: return dict(design_)
    ref = re.compile(rf"(#{re.escape(old)})(?!\d)")
    decl = re.compile(rf"(\b(?:id|for|aria-labelledby|aria-describedby)\s*=\s*[\"']){re.escape(old)}(?!\d)")
    def fix(text): return decl.sub(lambda m: m.group(1) + new, ref.sub("#" + new, text))
    return {k: (fix(v) if isinstance(v, str) and k in ("html", "css") else v) for k, v in design_.items()}


@app.put("/api/projects/{pid}/script")
def update_script(pid: str, body: ScriptIn):
    """Save an edited script and bring the slides up to date, redesigning only the scenes that changed."""
    p = projects.get(pid)
    if not p: raise HTTPException(404)
    parse_or_422(body.script, body.title, body.subtitle)
    if body.script == p["script"]: return {"job": None, "changed": []}
    old = p["script"]
    remap, ids = align_slides(old, body.script) if p["versions"] else ({}, [])
    ids = [i for i in ids if i != "s0"]
    projects.set_script(pid, body.script)
    if not p["versions"]: return {"job": None, "changed": []}
    if ids and not config.api_key_status()["set"] and p["versions"][-1].get("mode") != "basic":
        raise HTTPException(400, "Add your Anthropic API key in Settings to redesign the changed slides.")
    last_mode = p["versions"][-1].get("mode", "design")
    if last_mode == "basic":
        return {"job": start_design(pid, mode="basic", note="Script edited"), "changed": ids}
    return {"job": start_design(pid, only=ids or None, feedback=edit_note(old, body.script, ids, remap), remap=remap,
                                note=f"Script edited ({len(ids)} slide{'s' if len(ids) != 1 else ''} redesigned)"), "changed": ids}


class ApplyIn(BaseModel):
    script: str | None = None
    requests: list[dict] = []


@app.post("/api/projects/{pid}/apply")
def apply_changes(pid: str, body: ApplyIn):
    """Bring the slides up to date with a script edit and any visual requests together, in one design run that touches only what changed."""
    p = projects.get(pid)
    if not p or not p["versions"]: raise HTTPException(404, "Design the slides first.")
    text = body.script if body.script is not None else p["script"]
    m = parse_or_422(text)
    reqs = [{"slides": [x for x in r.get("slides", []) if re.fullmatch(r"s\d+", str(x)) and int(x[1:]) <= len(m.slides)], "request": str(r.get("request", "")).strip()}
            for r in body.requests if str(r.get("request", "")).strip()]
    last_mode = p["versions"][-1].get("mode", "design")
    if reqs and last_mode == "basic": raise HTTPException(400, "Visual changes need the Claude design. Press 'Design with Claude' first.")
    if not config.api_key_status()["set"] and (reqs or last_mode != "basic"): raise HTTPException(400, "Add your Anthropic API key in Settings first.")
    old = p["script"]
    remap, ids = align_slides(old, text) if text != old else ({f"s{i + 1}": f"s{i + 1}" for i in range(len(m.slides))}, [])
    ids = [i for i in ids if i != "s0"]
    if text != old: projects.set_script(pid, text)
    if last_mode == "basic" and not reqs:
        return {"job": start_design(pid, mode="basic", note="Script edited"), "changed": ids} if text != old else {"job": None, "changed": []}
    scoped = sorted({i for r in reqs for i in r["slides"]}, key=lambda x: int(x[1:]))
    whole = any(not r["slides"] for r in reqs)
    only = None if whole else sorted(set(ids) | set(scoped), key=lambda x: int(x[1:]))
    if not whole and not only: return {"job": None, "changed": []}
    feedback = "\n".join(x for x in [edit_note(old, text, ids, remap) if ids else "",
        ("Visual changes the author asked for:\n" + "\n".join(f"- {('slides ' + ', '.join(r['slides'])) if r['slides'] else 'the whole module'}: {r['request']}" for r in reqs)) if reqs else ""] if x)
    for r in reqs: projects.add_feedback(pid, r["request"], r["slides"] or "all")
    parts = ([f"script edited ({len(ids)} slide{'s' if len(ids) != 1 else ''})"] if ids else []) + ([f"{len(reqs)} visual change{'s' if len(reqs) != 1 else ''}"] if reqs else [])
    return {"job": start_design(pid, only=only, feedback=feedback, remap=remap, note="Assistant: " + " and ".join(parts)), "changed": ids}


@app.post("/api/projects/{pid}/design")
def design_project(pid: str, body: GenerateIn):
    """Design a module's slides for the first time (with Claude, or as the quick layout), or upgrade a quick layout to Claude's design."""
    p = projects.get(pid)
    if not p: raise HTTPException(404)
    parse_or_422(body.script, body.title, body.subtitle)
    if body.mode == "design" and not config.api_key_status()["set"]:
        raise HTTPException(400, "Designing slides needs an Anthropic API key. Add one in Settings, or choose the quick layout.")
    projects.set_script(pid, body.script)
    note = ("First design" if body.mode == "design" else "Quick layout") if not p["versions"] else "Designed with Claude"
    return {"job": start_design(pid, note=note, mode=body.mode), "changed": []}


class RestoreIn(BaseModel):
    version: int


@app.post("/api/projects/{pid}/restore")
def restore(pid: str, body: RestoreIn):
    try: projects.restore(pid, body.version)
    except ValueError as e: raise HTTPException(400, str(e))
    return project_view(pid)


class LabelIn(BaseModel):
    label: str = ""


@app.patch("/api/projects/{pid}/versions/{n}")
def label_version(pid: str, n: int, body: LabelIn):
    """Name a version ("Sent to legal"); an empty name clears it."""
    if not projects.get(pid): raise HTTPException(404, "That module wasn't found.")
    try: p = projects.set_label(pid, n, body.label)
    except ValueError as e: raise HTTPException(400, str(e))
    return {"n": n, "label": next(v for v in p["versions"] if v["n"] == n).get("label", "")}


def _diff_rows(old_lines, new_lines, context=2):
    """A readable line diff: lines only in the old text ("del"), only in the new ("add"), and a little context around them."""
    import difflib
    rows = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False).get_opcodes():
        if op == "equal":
            keep = old_lines[i1:i2]
            if len(keep) > 2 * context + 2:
                rows += [{"op": "same", "text": t} for t in keep[:context]] + [{"op": "gap", "n": len(keep) - 2 * context}] + [{"op": "same", "text": t} for t in keep[-context:]]
            else: rows += [{"op": "same", "text": t} for t in keep]
        else:
            rows += [{"op": "del", "text": t} for t in old_lines[i1:i2]] + [{"op": "add", "text": t} for t in new_lines[j1:j2]]
    return rows


def _slide_state(pid, a):
    """How the slides of version `a` relate to the current version's: each is the same, changed or gone since, and which can be taken back."""
    p = projects.get(pid)
    cur_text = projects.version_script(pid, p["current"]) or p["script"]
    a_text = projects.version_script(pid, a)
    if a_text is None: raise HTTPException(404, "That version doesn't exist.")
    old, new = script.parse(cur_text), script.parse(a_text)
    remap, changed = align_slides(cur_text, a_text)                       # version a's slide id -> the current one it matches
    reason = ""
    try: chat.slide_blocks(a_text); chat.slide_blocks(cur_text)
    except ValueError as e: reason = str(e)
    if not reason and not (projects.slides(pid, a) and projects.slides(pid, p["current"])): reason = "A quick layout has no separate slide designs to take back. Restore the whole version instead."
    rows = [{"id": "s0", "title": "Title slide", "status": "changed" if "s0" in changed else "same", "now": "s0"}]
    for i, sl in enumerate(new.slides, 1):
        sid = f"s{i}"
        rows.append({"id": sid, "title": sl.title, "status": "removed" if sid not in remap else "changed" if sid in changed else "same", "now": remap.get(sid)})
    mapped = set(remap.values())
    added = [{"id": f"s{i}", "title": sl.title} for i, sl in enumerate(old.slides, 1) if f"s{i}" not in mapped]
    return {"p": p, "cur_text": cur_text, "a_text": a_text, "remap": remap, "changed": changed, "rows": rows, "added": added, "reason": reason}


@app.get("/api/projects/{pid}/compare")
def compare_version(pid: str, a: int):
    """What differs between an earlier version and the current one: the script line by line, and slide by slide."""
    if not projects.get(pid): raise HTTPException(404, "That module wasn't found.")
    st = _slide_state(pid, a)
    return {"a": a, "b": st["p"]["current"], "script": _diff_rows(st["a_text"].splitlines(), st["cur_text"].splitlines()),
            "slides": [{**r, "restorable": not st["reason"] and r["status"] != "same"} for r in st["rows"]], "added": st["added"], "reason": st["reason"],
            "has_draft": st["p"].get("draft") is not None}


class RestoreSlideIn(BaseModel):
    version: int
    slide: str


@app.post("/api/projects/{pid}/restore-slide")
def restore_slide(pid: str, body: RestoreSlideIn):
    """Take one slide (its words and its design) back from an earlier version, as a new version. No Claude call: the slide's saved
    design comes back as it was, and the checker looks over the result."""
    if not projects.get(pid): raise HTTPException(404, "That module wasn't found.")
    st = _slide_state(pid, body.version); p = st["p"]
    if st["reason"]: raise HTTPException(400, st["reason"])
    if p.get("draft") is not None: raise HTTPException(409, "You have script changes that aren't in the slides yet. Update the slides (or undo those changes) first.")
    row = next((r for r in st["rows"] if r["id"] == body.slide), None)
    if row is None: raise HTTPException(400, "That slide isn't in that version.")
    if row["status"] == "same": raise HTTPException(400, "That slide is already the same in the current version.")
    head, blocks = chat.slide_blocks(st["a_text"])
    if body.slide == "s0": edits = [{"slide": "s0", "op": "header", "text": head}]
    elif row["status"] == "changed": edits = [{"slide": row["now"], "op": "replace", "text": blocks[int(body.slide[1:]) - 1]}]
    else:
        n = int(body.slide[1:])
        after = next((st["remap"][f"s{k}"] for k in range(n - 1, 0, -1) if f"s{k}" in st["remap"]), "s0")        # after the slide that came before it
        edits = [{"slide": after, "op": "insert_after", "text": blocks[n - 1]}]
    try: new_text = chat.apply_edits(st["cur_text"], edits); m = script.parse(new_text)
    except (ValueError, script.ScriptError) as e: raise HTTPException(400, f"That slide couldn't be put back: {e}")
    cur_slides, old_slides = projects.slides(pid), projects.slides(pid, body.version)
    remap, changed = align_slides(st["cur_text"], new_text)               # the new script's slide id -> the current one it was
    slides = {nid: remap_design(cur_slides[oid], oid, nid) for nid, oid in remap.items() if oid in cur_slides and nid not in changed}
    for nid in [c for c in changed if c != "s0"]:                         # the slide that came back brings its own design
        if body.slide not in old_slides: raise HTTPException(400, "That slide's design wasn't saved.")
        slides[nid] = remap_design(old_slides[body.slide], body.slide, nid)
    with design_lock:
        page, issues, _ = design._check(m, config.brand(), slides, config.glossary()["banned"], config.motion(), new_text, config.glossary())
        if not page: raise HTTPException(400, "The slides didn't assemble: " + "; ".join(i.message for i in issues[:3]))
        projects.save_version(pid, page, slides, f"Restored “{row['title']}” from version {body.version}", issues=issues, script_text=new_text, mode="design")
    return project_view(pid)


@app.post("/api/projects/{pid}/to-video")
def to_video(pid: str):
    p = projects.get(pid)
    if not p or not p["versions"]: raise HTTPException(404, "Design the slides first.")
    page = (projects.folder(pid) / "module.html").read_bytes()
    return register_upload(f"{p['name']}.html", page) | {"project": pid}


@app.get("/api/settings/glossary")
def get_glossary(): return config.glossary()


@app.put("/api/settings/glossary")
def put_glossary(changes: dict): return config.set_glossary(changes)


# ---------------------------------------------------------------- main

def free_port(start=8765):
    for port in range(start, start + 50):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)): return port
    raise SystemExit("No free port found between 8765 and 8815.")


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    load_jobs()
    for lane in queues: threading.Thread(target=worker, args=(lane,), daemon=True).start()
    threading.Thread(target=warm_up, daemon=True).start()
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    print(f"\n  html2mp4 Studio is running at {url}\n  Videos are saved to {OUTPUT}\n  Keep this window open while you work. Press Ctrl+C to quit.\n", flush=True)
    if not os.environ.get("HTML2MP4_NO_BROWSER"):
        threading.Timer(1.2, webbrowser.open, [url]).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
