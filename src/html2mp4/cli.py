"""html2mp4 — render a narrated HTML slide module to a professional 1080p MP4.

Works with HTML modules built on the narrated-slides template (see examples/):
  * narration in  <script> var scenes = [{id:'s0', chunks:["...", ...]}, ...]
  * one  <section id="sN" class="slide">  per scene
  * animated elements tagged  data-c="<chunk index>"  (optional data-d="<delay s>")

Pipeline (fully local, no cloud services):
  1. narration  — Kokoro neural TTS, cached per sentence
  2. timeline   — sentences laid out with natural pauses; slides held until their animations finish
  3. video      — headless Chromium, every CSS transition paused and seeked per frame (exact sync),
                  rendered in parallel segments, H.264 High @ 1080p30, BT.709
  4. audio      — voice cleanup + EBU R128 loudness (-16 LUFS), optional music bed with auto-ducking
  5. captions   — embedded switchable subtitle track + .srt/.vtt sidecars

usage:
  html2mp4 module.html                          # -> module.mp4 (+ .srt/.vtt) next to the HTML
  html2mp4 module.html --music none             # no background music
  html2mp4 module.html --preview 10 -o preview.mp4   # first 10 seconds only
  html2mp4 module.html --quality 1440p --music-volume present
"""
import argparse, hashlib, json, os, pathlib, re, shutil, subprocess, sys, textwrap, time
from concurrent.futures import ProcessPoolExecutor
import numpy as np, soundfile as sf

from html2mp4 import music as music_beds

os.environ.setdefault("HF_HUB_VERBOSITY", "error")     # hide the Hugging Face rate-limit notice
CACHE = pathlib.Path(os.environ.get("HTML2MP4_CACHE", pathlib.Path.home() / ".cache" / "html2mp4"))


def _find_ffmpeg():
    """System ffmpeg if installed, else the static build bundled with imageio-ffmpeg (no Homebrew needed)."""
    if shutil.which("ffmpeg"): return shutil.which("ffmpeg")
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


FFMPEG = _find_ffmpeg()


# Set by the Studio while a preview is being made: pausable renders (full videos) hold their frame workers
# so the preview gets the whole machine, then carry on exactly where they stopped.
RENDER_PAUSE = __import__("threading").Event()


class Cancelled(Exception):
    """The conversion was stopped on request."""


class ConversionError(Exception):
    """A problem with the input or settings, with a message meant for the person converting."""
RENDER_VERSION = 5                      # bump to invalidate cached video renders

FPS = 30
# Output size; the stage is rendered natively at that scale (vector-sharp, never upscaled). 1440p keeps colour detail at
# the stage's own resolution despite web video's half-resolution colour (4:2:0), so small coloured text stays crisp.
QUALITIES = {"1440p": (2560, 1440), "1080p": (1920, 1080)}
CRF = 17                         # measured within ~0.5 dB of lossless 4:2:0 on slide content, at ~2-3 MB per minute
MUSIC_VOLUMES = {"subtle": 17.0, "balanced": 12.0, "present": 8.0}   # dB the music sits under the voice while speaking
TTS_SR, SR = 24000, 48000

# pacing (seconds)
PRE_ROLL     = 0.6                      # silence before the first word
VISUAL_LEAD  = 0.0                      # like the page's own player: visuals start exactly with their sentence
CHUNK_GAP    = 0.45                     # breath between sentences
SCENE_GAP    = 0.9                      # extra pause before a slide change
SETTLE_HOLD  = 0.6                      # fully built slide stays up this long before cutting
END_HOLD     = 1.6                      # hold on the last frame
FADE_OUT     = 0.8                      # sound fades at the very end (the picture holds the last slide, as the page does)

PAGE_CSS = "#bar,#start{display:none!important}#frame{inset:0!important}#stage{transform:none!important}"

PAGE_JS = """
(ids) => {
  const scenes = ids.map(id => document.getElementById(id));
  const items = scenes.map(s => [...s.querySelectorAll('[data-c]')]);
  items.flat().forEach(e => { const d = e.getAttribute('data-d'); if (d) e.style.setProperty('--d', d + 's'); });
  const stage = document.getElementById('stage');
  const started = new Map();
  const secs = v => v.split(',').map(x => parseFloat(x) * (x.trim().endsWith('ms') ? 0.001 : 1));
  const span = e => {                     // longest delay+duration of the element's transitions/animations
    const cs = getComputedStyle(e); let m = 0;
    const pairs = [[cs.transitionDelay, cs.transitionDuration]];
    if (cs.animationName !== 'none') pairs.push([cs.animationDelay, cs.animationDuration]);
    pairs.forEach(([d, u]) => { d = secs(d); secs(u).forEach((x, i) => m = Math.max(m, x + (d[i % d.length] || 0))); });
    return m;
  };
  const seek = t => document.getAnimations().forEach(a => {
    if (!started.has(a)) { started.set(a, t); a.pause(); }
    a.currentTime = Math.max(0, (t - started.get(a)) * 1000);
  });
  window.__html2mp4 = {
    size: () => [stage.offsetWidth, stage.offsetHeight],
    spans: () => items.map(list => { const m = {}; list.forEach(e => { const c = +e.dataset.c; m[c] = Math.max(m[c] || 0, span(e)); }); return m; }),
    reset: () => {
      scenes.forEach(s => s.classList.remove('active'));
      items.flat().forEach(e => e.classList.remove('on'));
      document.getAnimations().forEach(a => a.finish());
      started.clear();
    },
    show: (si, ci, t) => {                // same rule as the page's own render()
      seek(t);
      scenes.forEach((s, i) => s.classList.toggle('active', i === si));
      items.forEach((list, i) => list.forEach(e => e.classList.toggle('on', i < si || (i === si && +e.dataset.c <= ci))));
      seek(t);
    },
    frame: t => seek(t),
  };
}
"""


def log(msg): print(f"[html2mp4] {msg}", flush=True)


def run(cmd, **kw): return subprocess.run([str(c) for c in cmd], check=True, **kw)


# ---------------------------------------------------------------- script

def load_scenes(html_text):
    m = re.search(r"var scenes = \[(.*?)\];", html_text, re.S)
    if not m: raise ConversionError("This file doesn't contain a narration script, so it isn't a narrated slide module. "
                                    "Check you picked the right file (technical detail: no `var scenes = [...]` list).")
    scenes = []
    for s in re.finditer(r"\{\s*id\s*:\s*['\"]([^'\"]+)['\"]\s*,\s*chunks\s*:\s*\[(.*?)\]\s*\}", m.group(1), re.S):
        chunks = [json.loads('"' + c + '"') for c in re.findall(r'"((?:[^"\\]|\\.)*)"', s.group(2))]
        scenes.append({"id": s.group(1), "chunks": chunks})
    if not scenes or not any(s["chunks"] for s in scenes):
        raise ConversionError("The narration script in this file is empty.")
    missing = [s["id"] for s in scenes if f'id="{s["id"]}"' not in html_text and f"id='{s['id']}'" not in html_text]
    if missing: raise ConversionError(f"The script mentions slide(s) {', '.join(missing)}, but the page has no element with that id.")
    if 'id="stage"' not in html_text: raise ConversionError('The page needs a fixed-size <div id="stage"> that holds the slides.')
    return scenes


def page_title(html_text, fallback):
    m = re.search(r"<title>(.*?)</title>", html_text, re.S)
    return __import__("html").unescape(m.group(1).strip()) if m else fallback


# ---------------------------------------------------------------- narration

def short_espeak_data_path():
    """espeak-ng (the fallback phonemizer for unknown words) silently ignores data paths longer than
    ~160 chars (and resolves symlinks), which deep install locations exceed — use a copy in the cache."""
    import espeakng_loader
    from importlib.metadata import version
    from misaki import espeak  # noqa: F401  (configures the library and default data path)
    from phonemizer.backend.espeak.wrapper import EspeakWrapper
    data = espeakng_loader.get_data_path()
    if len(data) < 120: return
    short = CACHE / f"espeak-ng-data-{version('espeakng-loader')}"
    if not short.exists():
        shutil.copytree(data, short.with_suffix(".tmp"), dirs_exist_ok=True)
        short.with_suffix(".tmp").rename(short)
    EspeakWrapper.set_data_path(str(short))


_PIPELINES = {}
_TTS_LOCK = __import__("threading").Lock()     # one synthesis at a time (Studio previews vs. renders)


def kokoro_pipeline(lang):
    """Load Kokoro once per language and keep it (loading takes a few seconds)."""
    if lang not in _PIPELINES:
        short_espeak_data_path()
        from kokoro import KPipeline
        import torch
        torch.set_num_threads(max(1, min(4, (os.cpu_count() or 4) // 2)))   # many threads thrash when the CPU is busy
        _PIPELINES[lang] = KPipeline(lang_code=lang, repo_id="hexgrad/Kokoro-82M")
    return _PIPELINES[lang]


def synthesize(scenes, voice, speed, cache, progress=lambda f: None):
    cache.mkdir(parents=True, exist_ok=True)
    key = lambda text: cache / f"{voice}_{speed}_{hashlib.sha1(text.encode()).hexdigest()[:12]}.wav"
    todo = [c for sc in scenes for c in sc["chunks"] if not key(c).exists()]
    if todo:
        log(f"narrating {len(todo)} sentence(s) with Kokoro voice '{voice}' at {speed}x")
        import warnings; warnings.filterwarnings("ignore")
        with _TTS_LOCK:
            _synthesize_todo(todo, voice, speed, key, progress)
    return [[sf.read(key(c), dtype="float32")[0] for c in sc["chunks"]] for sc in scenes]


def _synthesize_todo(todo, voice, speed, key, progress):
    pipe = kokoro_pipeline(voice[0])
    for i, text in enumerate(todo):
        progress(i / len(todo))
        if key(text).exists(): continue                                # made meanwhile by another caller
        a = np.concatenate([x.numpy() for _, _, x in pipe(text, voice=voice, speed=speed)])
        idx = np.where(np.abs(a) > 0.004)[0]                           # trim silence, keep 30 ms
        pad = int(0.03 * TTS_SR)
        sf.write(key(text), a[max(0, idx[0] - pad): idx[-1] + pad], TTS_SR)


# ---------------------------------------------------------------- browser

def open_page(p, html, width=1920):
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1280, "height": 720})
    page.goto(html.as_uri(), wait_until="networkidle")
    w, h = page.evaluate("[document.getElementById('stage').offsetWidth, document.getElementById('stage').offsetHeight]")
    page.close()
    page = browser.new_page(viewport={"width": w, "height": h}, device_scale_factor=width / w)
    page.goto(html.as_uri(), wait_until="networkidle")
    page.evaluate("document.fonts.ready")
    page.add_style_tag(content=PAGE_CSS)
    return browser, page


def measure_spans(html, ids):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page = open_page(p, html)
        page.evaluate(PAGE_JS, ids)
        spans = page.evaluate("__html2mp4.spans()")
        browser.close()
    return spans


# ---------------------------------------------------------------- timeline

def build_timeline(scenes, audio, spans):
    t, events, clips = PRE_ROLL, [], []
    for si, sc in enumerate(scenes):
        if si: t += SCENE_GAP
        visual_end = 0
        for ci, text in enumerate(sc["chunks"]):
            a = audio[si][ci]
            ev = max(0.0, t - VISUAL_LEAD)
            events.append((ev, si, ci))
            clips.append((t, a, text))
            visual_end = max(visual_end, ev + spans[si].get(str(ci), 0) + SETTLE_HOLD)
            t += len(a) / TTS_SR + CHUNK_GAP
        t = max(t, visual_end)
    return events, clips, t - CHUNK_GAP + END_HOLD + FADE_OUT


# ---------------------------------------------------------------- video

def x264(crf, fast=False, threads=0):
    # High profile 4:2:0 = plays everywhere (browsers, LMSs, phones). Tuned for flat graphics and smooth gradients.
    return ["-c:v", "libx264", "-preset", "veryfast" if fast else "slow", "-tune", "animation", "-crf", str(crf),
            "-profile:v", "high", "-pix_fmt", "yuv420p", "-x264-params", "aq-mode=3",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-threads", str(threads)]


def render_segment(job):
    html, ids, events, f0, f1, total, out, q, (width, height), crf, fast, stop, threads, nice, pause = job
    if nice: os.nice(nice)              # background renders yield the CPU to interactive work (previews)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, page = open_page(p, pathlib.Path(html), width)
        page.evaluate(PAGE_JS, ids)
        page.evaluate("__html2mp4.reset()")
        cdp = page.context.new_cdp_session(page)
        vw, vh = page.viewport_size["width"], page.viewport_size["height"]
        clip = {"x": 0, "y": 0, "width": vw, "height": vh, "scale": width / vw}
        ff = subprocess.Popen([FFMPEG, "-y", "-hide_banner", "-loglevel", "error",
            "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "png", "-i", "-",
            "-vf", "scale=out_color_matrix=bt709:out_range=tv:flags=lanczos+accurate_rnd+full_chroma_int+full_chroma_inp",
            *x264(crf, fast, threads), out],
            stdin=subprocess.PIPE)
        ei = 0
        for f in range(f0, f1):
            if stop is not None and stop.is_set(): break
            while pause is not None and pause.is_set() and not stop.is_set(): time.sleep(0.2)
            t = f / FPS
            while ei < len(events) and events[ei][0] <= t:
                et, si, ci = events[ei]
                page.evaluate(f"__html2mp4.show({si},{ci},{et})"); ei += 1
            page.evaluate(f"__html2mp4.frame({t})")
            # CDP ignores the emulated device scale unless the clip carries it explicitly
            shot = cdp.send("Page.captureScreenshot", {"format": "png", "optimizeForSpeed": True, "clip": clip})
            import base64; png = base64.b64decode(shot["data"])
            if f == f0:                                                # PNG IHDR holds width/height
                size = (int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big"))
                if size != (width, height): raise RuntimeError(f"captured frames are {size}, expected {(width, height)}")
            ff.stdin.write(png)
            if q is not None and (f - f0) % 10 == 9: q.put(10)
        ff.stdin.close(); ff.wait(); browser.close()
    return out


def render_video(html, ids, events, total, work, workers, progress=lambda f: None, size=(1920, 1080), crf=CRF, fast=False,
                 cancel=None, nice=0, pausable=False):
    nframes = int(round(total * FPS))
    key = hashlib.sha256(json.dumps([RENDER_VERSION, html.read_text(), ids, events, nframes, FPS, size, crf, fast]).encode()).hexdigest()
    video, keyfile = work / "video.mp4", work / "video.key"
    if video.exists() and keyfile.exists() and keyfile.read_text() == key:
        log("video unchanged — reusing cached render"); return video
    workers = max(1, min(workers, nframes // (FPS * 3)))
    bounds = np.linspace(0, nframes, workers + 1).astype(int)
    segdir = work / "segments"; shutil.rmtree(segdir, ignore_errors=True); segdir.mkdir(parents=True)
    log(f"rendering {nframes} frames ({total:.1f}s) at {size[0]}x{size[1]}@{FPS} on {workers} worker(s)")
    t0 = time.time()
    threads = max(1, (os.cpu_count() or 4) // workers)          # each encoder gets its share; no oversubscription
    import multiprocessing, queue
    with multiprocessing.Manager() as mgr, ProcessPoolExecutor(workers) as ex:
        q, stop, pause = mgr.Queue(), mgr.Event(), mgr.Event()
        futures = [ex.submit(render_segment, (str(html), ids, events, int(bounds[i]), int(bounds[i + 1]), total,
                                              str(segdir / f"{i:03}.mp4"), q, size, crf, fast, stop, threads, nice,
                                              pause if pausable else None))
                   for i in range(workers)]
        done = 0
        while not all(f.done() for f in futures):
            if cancel is not None and cancel.is_set(): stop.set()
            if pausable: pause.set() if RENDER_PAUSE.is_set() else pause.clear()
            try: done += q.get(timeout=0.3); progress(min(1, done / nframes))
            except queue.Empty: pass
        segs = [f.result() for f in futures]
    if cancel is not None and cancel.is_set():
        shutil.rmtree(segdir, ignore_errors=True)
        raise Cancelled()
    log(f"frames rendered in {time.time() - t0:.0f}s")
    (segdir / "list.txt").write_text("".join(f"file '{s}'\n" for s in segs))
    run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0",
         "-i", segdir / "list.txt", "-c", "copy", video])
    keyfile.write_text(key); shutil.rmtree(segdir)
    return video


# ---------------------------------------------------------------- audio

def loudnorm(src, dst, pre="", post="", target=-16, extra=()):
    """Two-pass EBU R128 normalisation (linear) with optional filters before/after."""
    lead = f"{pre}," if pre else ""
    err = run([FFMPEG, "-hide_banner", "-i", src, "-af",
               f"{lead}loudnorm=I={target}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
              capture_output=True, text=True).stderr
    m = json.loads(err[err.rindex("{"): err.rindex("}") + 1])
    ln = (f"loudnorm=I={target}:TP=-1.5:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    tail = f",{post}" if post else ""
    run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", src, "-af",
         f"{lead}{ln},aresample={SR}:filter_type=kaiser:filter_size=64{tail}", "-ar", SR, *extra, dst])


def resolve_music(arg):
    if not arg or arg == "none": return None
    if arg in music_beds.STYLES: return music_beds.ensure(arg, CACHE / "music")
    p = pathlib.Path(arg).expanduser()
    if not p.exists(): raise ConversionError(f"Music '{arg}' not found — use {', '.join(music_beds.STYLES)}, none, or an audio file.")
    return p


def master_audio(clips, total, music, music_level, work):
    mix = np.zeros(int((total + 1) * TTS_SR), dtype=np.float32)
    for t, a, _ in clips:
        i = int(round(t * TTS_SR)); seg = mix[i:i + len(a)]; seg += a[:len(seg)]
    sf.write(work / "voice_raw.wav", mix[: int(total * TTS_SR)], TTS_SR)
    loudnorm(work / "voice_raw.wav", work / "voice.wav",
             pre="highpass=f=70,acompressor=threshold=-21dB:ratio=2.2:attack=8:release=120")
    voice, _ = sf.read(work / "voice.wav", dtype="float32")
    fade = f"afade=t=out:st={total - FADE_OUT:.3f}:d={FADE_OUT}"
    final = work / "final.wav"

    if music is None:
        run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", work / "voice.wav",
             "-af", fade, "-ac", 2, final]); return final

    log(f"mixing music bed '{music.name}' ({music_level} dB under the voice, auto-ducked)")
    n = len(voice)
    # cut the music's low end (standard under narration): leaves room for the voice and keeps the music
    # audible on laptop and phone speakers, which can't reproduce bass anyway
    raw = run([FFMPEG, "-hide_banner", "-loglevel", "error", "-stream_loop", "-1", "-i", music,
               "-t", f"{n / SR:.3f}", "-af", "highpass=f=140:poles=2", "-ac", 2, "-ar", SR, "-f", "f32le", "-"],
              capture_output=True).stdout
    bed = np.frombuffer(raw, dtype=np.float32).reshape(-1, 2)[:n]
    bed = np.pad(bed, ((0, n - len(bed)), (0, 0)))
    import pyloudnorm
    bed = bed * 10 ** ((-16 - pyloudnorm.Meter(SR).integrated_loudness(bed)) / 20)

    # ducking: music sits `music_level` dB under the voice while speaking, rises 6 dB in pauses
    hop = SR // 100
    speaking = np.zeros(n // hop + 1)
    for t, a, _ in clips:
        speaking[int((t - 0.25) * 100): int((t + len(a) / TTS_SR + 0.35) * 100)] = 1
    target = np.where(speaking > 0, -music_level, -music_level + 6.0)
    g, cur = np.empty_like(target), target[0]
    for i, x in enumerate(target):                                    # smooth: 0.3 s down, 0.9 s up
        cur += (x - cur) * (1 - np.exp(-1 / (100 * (0.3 if x < cur else 0.9))))
        g[i] = cur
    gain = 10 ** (np.interp(np.arange(n) / hop, np.arange(len(g)), g) / 20)
    gain *= np.clip(np.arange(n) / (2.0 * SR), 0, 1)                  # 2 s music fade-in
    out = voice[:, None] + bed * gain[:, None]
    sf.write(work / "mix_raw.wav", out, SR, subtype="FLOAT")
    loudnorm(work / "mix_raw.wav", final, pre="alimiter=limit=0.8:level=false", post=fade)
    return final


# ---------------------------------------------------------------- captions

def balanced_cues(text, max_chars=80):
    """Split a sentence into the fewest cues of ≤2×42 chars, with evenly sized cues (no orphan words)."""
    words = text.split()
    for n in range(1, len(words) + 1):
        target, groups, cur = len(text) / n, [], []
        for w in words:
            if cur and len(" ".join(cur + [w])) > target + 8 and len(groups) < n - 1:
                groups.append(" ".join(cur)); cur = []
            cur.append(w)
        groups.append(" ".join(cur))
        if all(len(g) <= max_chars and len(textwrap.wrap(g, max(len(g) // 2 + 6, 24))) <= 2 for g in groups):
            return groups
    return [text]


def captions(clips, srt, vtt):
    cues = []
    for t, a, text in clips:
        sentences = []                                                 # break at sentence ends,
        for s in re.split(r"(?<=[.?!])\s+(?=[A-Z])", text):            # but keep short ones ("Select.")
            sentences.append(f"{sentences.pop()} {s}" if sentences and len(sentences[-1]) < 24 else s)
        groups = [g for s in sentences for g in balanced_cues(s)]
        dur, chars, acc = len(a) / TTS_SR, sum(map(len, groups)), 0
        for grp in groups:
            k = len(grp)
            lines = textwrap.wrap(grp, max(len(grp) // 2 + 6, 24)) if len(grp) > 42 else [grp]
            cues.append((t + dur * acc / chars, t + dur * (acc + k) / chars, "\n".join(lines))); acc += k

    def ts(x, sep):
        ms = int(round(x * 1000)); return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02}{sep}{ms % 1000:03}"
    srt.write_text("".join(f"{i}\n{ts(a, ',')} --> {ts(b, ',')}\n{x}\n\n" for i, (a, b, x) in enumerate(cues, 1)))
    vtt.write_text("WEBVTT\n\n" + "".join(f"{ts(a, '.')} --> {ts(b, '.')}\n{x}\n\n" for a, b, x in cues))


# ---------------------------------------------------------------- convert

VOICES = {   # curated Kokoro voices: id -> (name, description)
    "af_heart":   ("Heart",   "Warm and friendly · US female"),
    "af_bella":   ("Bella",   "Bright and upbeat · US female"),
    "am_michael": ("Michael", "Calm and assured · US male"),
    "am_fenrir":  ("Fenrir",  "Deep and steady · US male"),
    "bf_emma":    ("Emma",    "Clear and polished · UK female"),
    "bm_george":  ("George",  "Measured and classic · UK male"),
}

# share of the overall progress bar each step takes (rendering frames dominates)
STEPS = [("voice", "Recording the voiceover", 0.14), ("layout", "Timing the animations", 0.03),
         ("frames", "Animating the slides", 0.72), ("audio", "Mixing the sound", 0.08), ("finish", "Finishing up", 0.03)]


def convert(html, out=None, voice="af_heart", speed=0.90, music="gentle-pulse", music_volume="balanced",
            scenes_limit=None, workers=None, progress=None, quality="1440p", preview_seconds=None, cancel=None,
            nice=0, pausable=False):
    """Convert one module. `progress(fraction, label)` is called as work advances. Returns a summary dict.

    music_volume: "subtle" | "balanced" | "present", or dB under the voice while it speaks.
    preview_seconds: render only the opening N seconds (quicker encode), for trying out settings.
    cancel: a threading.Event; when set, the conversion stops at the next sentence or frame and raises Cancelled.
    nice: run the frame renderers at lower OS priority (e.g. 10) so they don't starve interactive work.
    pausable: let RENDER_PAUSE hold this render's frame workers (used for full videos while a preview is made)."""
    if quality not in QUALITIES: raise ConversionError(f"Unknown quality '{quality}' — use {', '.join(QUALITIES)}.")
    music_level = MUSIC_VOLUMES[music_volume] if music_volume in MUSIC_VOLUMES else float(music_volume)
    html = pathlib.Path(html).resolve()
    if not html.exists(): raise ConversionError(f"{html} not found")
    out = pathlib.Path(out or html.with_suffix(".mp4")).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    workers = workers or max(1, (os.cpu_count() or 4) // 2)
    # cache is per input (not per output) so music/caption variants reuse the rendered picture
    tag = hashlib.sha1(html.read_bytes()).hexdigest()[:8]                   # same content -> same cache
    suffix = (f"-scenes{scenes_limit}" if scenes_limit else "") + (f"-preview{preview_seconds:g}" if preview_seconds else "")
    work = CACHE / "renders" / f"{html.stem}-{tag}-{quality}{suffix}"
    work.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    def report(f, label):
        if cancel is not None and cancel.is_set(): raise Cancelled()
        if progress: progress(f, label)
    names = [n for n, _, _ in STEPS]
    def step(name):
        k = names.index(name)
        start, (_, label, weight) = sum(w for _, _, w in STEPS[:k]), STEPS[k]
        report(start, label)
        return lambda f: report(start + weight * f, label)

    text = html.read_text(encoding="utf-8")
    scenes = load_scenes(text)[:scenes_limit]
    ids = [s["id"] for s in scenes]
    music_path = resolve_music(music)
    log(f"{html.name}: {len(scenes)} scene(s), {sum(len(s['chunks']) for s in scenes)} sentences")

    voice_progress = step("voice")
    spans = measure_spans(html, ids)
    if preview_seconds:      # narrate only as many scenes as the preview needs
        for n in range(1, len(scenes) + 1):
            audio = synthesize(scenes[:n], voice, speed, CACHE / "tts", voice_progress)
            events, clips, total = build_timeline(scenes[:n], audio, spans[:n])
            if total >= preview_seconds: break
        total = min(total, float(preview_seconds))
        events = [e for e in events if e[0] < total]
        clips = [c for c in clips if c[0] < total]
    else:
        audio = synthesize(scenes, voice, speed, CACHE / "tts", voice_progress)
        events, clips, total = build_timeline(scenes, audio, spans)
    step("layout")
    video = render_video(html, ids, events, total, work, workers, step("frames"), cancel=cancel, nice=nice, pausable=pausable,
                         size=QUALITIES[quality], fast=bool(preview_seconds))
    step("audio")
    wav = master_audio(clips, total, music_path, music_level, work)
    step("finish")
    srt, vtt = out.with_suffix(".srt"), out.with_suffix(".vtt")
    captions(clips, srt, vtt)
    title = page_title(text, html.stem)
    run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", video, "-i", wav, "-i", srt,
         "-map", "0:v", "-map", "1:a", "-map", "2:s", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-c:s", "mov_text", "-metadata:s:a:0", "language=eng", "-metadata:s:s:0", "language=eng",
         "-metadata", f"title={title}", "-movflags", "+faststart", out])
    report(1.0, "Done")
    log(f"done in {time.time() - t0:.0f}s → {out}  ({total:.1f}s, captions: {srt.name}, {vtt.name})")
    return {"mp4": out, "srt": srt, "vtt": vtt, "title": title, "duration": total, "seconds": time.time() - t0}


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("html", type=pathlib.Path)
    ap.add_argument("-o", "--out", type=pathlib.Path, help="output .mp4 (default: next to the HTML)")
    ap.add_argument("--voice", default="af_heart", help=f"Kokoro voice ({', '.join(VOICES)}, ...)")
    ap.add_argument("--speed", type=float, default=0.90, help="narration speed (default 0.90)")
    ap.add_argument("--music", default="gentle-pulse", help=f"background music: {', '.join(music_beds.STYLES)} (built-in, default gentle-pulse), path to any audio file, or none")
    ap.add_argument("--music-volume", default="balanced",
                    help=f"music loudness under the voice: {', '.join(MUSIC_VOLUMES)} (default balanced), or dB below the voice")
    ap.add_argument("--quality", default="1440p", choices=list(QUALITIES), help="output resolution (default 1440p, sharpest)")
    ap.add_argument("--preview", type=float, metavar="SECONDS", help="render only the first SECONDS (to try settings)")
    ap.add_argument("--scenes", type=int, help="only render the first N scenes")
    ap.add_argument("--workers", type=int, help="parallel render processes (default: half the CPU cores)")
    a = ap.parse_args()

    shown = {"label": None, "pct": -10}
    def progress(f, label):
        pct = int(f * 100)
        if label != shown["label"] or pct >= shown["pct"] + 10:
            print(f"[html2mp4] {pct:3d}%  {label}", flush=True); shown.update(label=label, pct=pct)
    try:
        convert(a.html, a.out, a.voice, a.speed, a.music, a.music_volume, a.scenes, a.workers, progress,
                quality=a.quality, preview_seconds=a.preview)
    except ConversionError as e:
        sys.exit(f"[html2mp4] error: {e}")


if __name__ == "__main__":
    main()
