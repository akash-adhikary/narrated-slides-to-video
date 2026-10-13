"""html2mp4 Studio — a local web app for turning narrated HTML modules into videos.

usage: html2mp4-studio            # opens http://127.0.0.1:8765 in your browser
Videos are saved to ~/Downloads/Narrated Videos (override with HTML2MP4_OUTPUT).
"""
import json, os, pathlib, queue, re, shutil, socket, subprocess, sys, threading, time, uuid, webbrowser

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from html2mp4 import cli, music as music_beds

HOME = cli.CACHE / "studio"
UPLOADS, PREVIEWS = HOME / "uploads", HOME / "previews"
JOBS_FILE = HOME / "jobs.json"
OUTPUT = pathlib.Path(os.environ.get("HTML2MP4_OUTPUT", pathlib.Path.home() / "Downloads" / "Narrated Videos"))
INDEX = pathlib.Path(__file__).with_name("studio.html")
SAMPLE_TEXT = "Hi there. I'll be narrating your module, clearly and at a comfortable pace."
MUSIC_INFO = {
    "gentle-pulse": ("Gentle pulse", "Soft chords with a light, steady rhythm"),
    "calm-pad":     ("Calm pad", "Warm, ambient and unobtrusive"),
    "warm-keys":    ("Warm keys", "Mellow electric piano"),
}

app = FastAPI(title="html2mp4 Studio", docs_url=None, redoc_url=None)
jobs: dict[str, dict] = {}
job_queue: "queue.Queue[str]" = queue.Queue()


# ---------------------------------------------------------------- helpers

def save_jobs():
    HOME.mkdir(parents=True, exist_ok=True)
    JOBS_FILE.write_text(json.dumps(jobs, indent=1, default=str))


def load_jobs():
    if JOBS_FILE.exists():
        for j in json.loads(JOBS_FILE.read_text()).values():
            if j["status"] in ("queued", "running"):        # interrupted by a restart
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
    if job["status"] == "running" and job.get("started"):
        elapsed, p = time.time() - job["started"], job.get("progress", 0)
        # the voice step's speed varies a lot, so trust the measured rate only once animating is under way
        j["eta"] = elapsed * (1 - p) / p if p > 0.3 else max(20, job.get("estimate", 120) - elapsed)
    return j


# ---------------------------------------------------------------- worker

def worker():
    while True:
        jid = job_queue.get()
        job = jobs[jid]
        job.update(status="running", started=time.time(), progress=0.0, label="Getting ready")
        def progress(f, label): job.update(progress=round(f, 4), label=label)
        try:
            out = unique_path(OUTPUT, job["title"], ".mp4")
            res = cli.convert(job["html_path"], out, job["voice"], job["speed"], job["music_arg"], progress=progress)
            job.update(status="done", progress=1.0, label="Done", finished=time.time(),
                       duration=res["duration"], files={k: str(res[k]) for k in ("mp4", "srt", "vtt")})
        except cli.ConversionError as e:
            job.update(status="failed", error=str(e))
        except Exception as e:  # noqa: BLE001 — surface anything unexpected to the user, keep serving
            job.update(status="failed", error=f"Something went wrong while creating the video ({type(e).__name__}: {e}).")
        save_jobs()


def warm_up():
    """Prepare the music beds and previews in the background so the first click is instant."""
    PREVIEWS.mkdir(parents=True, exist_ok=True)
    for style in music_beds.STYLES:
        dst = PREVIEWS / f"music-{style}.m4a"
        if not dst.exists(): to_m4a(music_beds.ensure(style, cli.CACHE / "music"), dst, seconds=24)
    for voice in cli.VOICES:
        if job_queue.qsize() or any(j["status"] == "running" for j in jobs.values()): return   # don't slow a render
        voice_sample(voice, 0.9)


# ---------------------------------------------------------------- API

@app.get("/", response_class=HTMLResponse)
def index(): return INDEX.read_text()


@app.get("/api/options")
def options():
    return {"voices": [{"id": k, "name": n, "desc": d} for k, (n, d) in cli.VOICES.items()],
            "music": [{"id": k, "name": n, "desc": d} for k, (n, d) in MUSIC_INFO.items()],
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


@app.post("/api/jobs")
def create_job(req: JobRequest):
    folder = UPLOADS / re.sub(r"\W", "", req.upload_id)
    htmls = list(folder.glob("*.htm*"))
    if not htmls: raise HTTPException(404, "That upload has expired — please choose the file again.")
    if req.voice not in cli.VOICES: raise HTTPException(400, "Unknown voice.")
    if req.music.startswith("upload:"):
        music_arg = str(UPLOADS / "music" / pathlib.Path(req.music[7:]).name)
    elif req.music in music_beds.STYLES or req.music == "none":
        music_arg = req.music
    else: raise HTTPException(400, "Unknown music choice.")
    text = htmls[0].read_text(encoding="utf-8", errors="replace")
    words = sum(len(c.split()) for s in cli.load_scenes(text) for c in s["chunks"])
    jid = uuid.uuid4().hex[:10]
    jobs[jid] = {"id": jid, "title": cli.page_title(text, htmls[0].stem), "filename": htmls[0].name,
                 "voice": req.voice, "speed": req.speed, "music": req.music, "music_arg": music_arg,
                 "html_path": str(htmls[0]), "status": "queued", "progress": 0.0, "label": "Waiting to start",
                 "created": time.time(), "estimate": 40 + words / (2.4 * req.speed) * 1.4}
    save_jobs(); job_queue.put(jid)
    return public(jobs[jid])


@app.get("/api/jobs")
def list_jobs(): return sorted((public(j) for j in jobs.values()), key=lambda j: -j["created"])


@app.get("/api/jobs/{jid}")
def get_job(jid: str):
    if jid not in jobs: raise HTTPException(404)
    return public(jobs[jid])


@app.delete("/api/jobs/{jid}")
def forget_job(jid: str):
    if jid in jobs and jobs[jid]["status"] not in ("queued", "running"):
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


# ---------------------------------------------------------------- main

def free_port(start=8765):
    for port in range(start, start + 50):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)): return port
    raise SystemExit("No free port found between 8765 and 8815.")


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    load_jobs()
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=warm_up, daemon=True).start()
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    print(f"\n  html2mp4 Studio is running at {url}\n  Videos are saved to {OUTPUT}\n  Keep this window open while you work. Press Ctrl+C to quit.\n", flush=True)
    if not os.environ.get("HTML2MP4_NO_BROWSER"):
        threading.Timer(1.2, webbrowser.open, [url]).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
