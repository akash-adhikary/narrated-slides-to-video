"""html2mp4 Studio — a local web app for turning narrated HTML modules into videos.

usage: html2mp4-studio            # opens http://127.0.0.1:8765 in your browser
Videos are saved to ~/Downloads/Narrated Videos (override with HTML2MP4_OUTPUT).
"""
import json, os, pathlib, queue, re, shutil, socket, subprocess, sys, threading, time, uuid, webbrowser

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from html2mp4 import brandkit, cli, compose, config, music as music_beds, script

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


@app.post("/api/inspect")
async def inspect(file: UploadFile = File(...)):
    if not re.search(r"\.html?$", file.filename or "", re.I):
        raise HTTPException(400, "Please choose an .html file.")
    uid = uuid.uuid4().hex[:12]
    folder = UPLOADS / uid; folder.mkdir(parents=True)
    path = folder / re.sub(r"[^\w.\- ]+", "_", file.filename)
    path.write_bytes(await file.read())
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        scenes = cli.load_scenes(text)
    except cli.ConversionError as e:
        shutil.rmtree(folder); raise HTTPException(422, str(e))
    words = sum(len(c.split()) for s in scenes for c in s["chunks"])
    sentences = sum(len(s["chunks"]) for s in scenes)
    return {"upload_id": uid, "filename": file.filename, "title": cli.page_title(text, path.stem),
            "scenes": scenes, "sentences": sentences, "words": words}


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
    return {"api_key": config.api_key_status(), "brand": config.brand(), "fonts": config.available_fonts()}


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
