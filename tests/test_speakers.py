"""A second speaker (a mascot who talks alongside the narrator), video clips in the media library, a talking character made from a
clip of it speaking, and cutting a subject out of a plain backdrop without being told where it is."""
import io, json, subprocess
import numpy as np
import pytest
from PIL import Image
from playwright.sync_api import sync_playwright
from html2mp4 import cli, compose, config, design, media, script
from test_studio import client, wait   # noqa: F401

SCENES = """Meet the team
Voice: Spotter = Puck
Scene 1: Hello (0:00–0:10)
Narration: "Welcome aboard. Here is our guide."
Spotter: "Hi, I'm Spotter!
I find answers."
Image: Spotter
Scene 2: Next
"So what do we build?

At the core is an agent."
Spotter: Woof. That's me.
"""


def test_a_script_names_a_second_speaker_and_gives_it_lines():
    m = script.parse(SCENES)
    assert m.voices == {"Spotter": "am_puck"} and m.title == "Meet the team"
    a, b = m.slides
    assert list(zip(a.say, a.speakers)) == [("Welcome aboard.", ""), ("Here is our guide.", ""), ("Hi, I'm Spotter!", "Spotter"), ("I find answers.", "Spotter")]
    assert list(zip(b.say, b.speakers)) == [("So what do we build?", ""), ("At the core is an agent.", ""), ("Woof.", "Spotter"), ("That's me.", "Spotter")]
    m2 = script.parse("Title: T\nVoice: Max = am_echo\n## A\nSay: Hello there.\nMax: Hi! I am here.\nSay: Bye.\n## B\nSay: Only me.\n")
    assert m2.voices == {"Max": "am_echo"} and m2.slides[0].speakers == ["", "Max", ""] and m2.slides[1].speakers == []
    assert script.parse("Title: T\nVoice: Max\n## A\nSay: Hi.\n").voices == {"Max": "am_puck"}         # a playful voice unless one is named
    assert script.parse("Title: T\n## A\nSay: Hi.\nNote: Max: not a speaker here\n").slides[0].speakers == []   # nobody declared: nobody else speaks
    with pytest.raises(script.ScriptError, match="no voice called"): script.parse("Title: T\nVoice: Max = Gandalf\n## A\nSay: Hi.\n")
    assert "(Spotter speaks)" in design._scenes_text(m, ["s1"]).splitlines()[-1]


def test_the_page_says_who_speaks_and_the_video_voices_each_speaker(tmp_path, monkeypatch):
    m = script.parse(SCENES)
    page = compose.assemble(m, config.brand(), [("custom", '<h2 class="t-heading" data-c="0">A</h2>'), ("custom", '<h2 class="t-heading" data-c="0">B</h2>')])
    assert 'var voices = {"Spotter": "am_puck"};' in page and 'who:{"2": "Spotter", "3": "Spotter"}' in page
    assert '#stage.speaking[data-speaker="Spotter"] .slide.active .h2m-sprite.h2m-char[data-speaker="Spotter"]::after{opacity:1}' in page
    scenes = cli.load_scenes(page)
    assert scenes[0]["who"] == {2: "Spotter", 3: "Spotter"} and scenes[0]["voices"] == {2: "am_puck", 3: "am_puck"} and "who" not in scenes[1] or scenes[1]["who"] == {2: "Spotter", 3: "Spotter"}
    assert compose.check(page, m) == []
    said = []                                                            # each sentence goes to its speaker's voice
    def fake(todo, voice, speed, key, progress, say=lambda t: t, need=lambda c: True):
        for t in todo:
            said.append((voice, t)); import soundfile as sf; sf.write(key(t), np.zeros(2400, np.float32), cli.TTS_SR); key(t).with_suffix(".json").write_text("[]")
    monkeypatch.setattr(cli, "_synthesize_todo", fake)
    audio = cli.synthesize(scenes, "af_heart", 0.9, tmp_path, timings=True)
    assert ("am_puck", "Hi, I'm Spotter!") in said and ("af_heart", "Welcome aboard.") in said and not any(v == "am_puck" and t == "Welcome aboard." for v, t in said)
    assert cli.pending(scenes, "af_heart", 0.9, tmp_path, timings=True) == 0 and len(audio[0]) == 4
    _, clips, _ = cli.build_timeline(scenes, audio, [{}, {}])
    assert [c[3] for c in clips[:4]] == ["", "", "Spotter", "Spotter"]          # the renderer knows who is talking when


def test_a_character_talks_only_while_its_speaker_does(tmp_path):
    talker = media.edit(media.add(_png(), "Spotter.png")["id"], "talk", {"mouth": [0.3, 0.5, 0.7, 0.7]}, name="Spotter (talking)")
    media.update(talker["id"], speaker="Spotter")
    plain = media.edit(media.add(_png(), "Host.png")["id"], "talk", {"mouth": [0.3, 0.5, 0.7, 0.7]}, name="Host (talking)")
    html, _ = media.resolve(f'<img data-asset="{talker["id"]}" alt="S"><img data-asset="{plain["id"]}" alt="H">')
    assert 'data-speaker="Spotter"' in html and html.count("data-speaker") == 1
    m = script.parse(SCENES)
    f = tmp_path / "m.html"; f.write_text(compose.assemble(m, config.brand(), [("custom", '<h2 class="t-heading" data-c="0">A</h2>' + html), ("custom", '<h2 data-c="0">B</h2>')]))
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(); pg.goto(f.as_uri())
        pg.evaluate(cli.PAGE_JS, ["s1", "s2"]); pg.evaluate("__html2mp4.reset()"); pg.evaluate("__html2mp4.show(0, 3, 0)")
        moving = lambda who: pg.evaluate(f"""() => {{ __html2mp4.frame(0.05, {json.dumps(who)});
            return [...document.querySelectorAll('#s1 .h2m-talk')].map(e => getComputedStyle(e).animationName); }}""")
        assert moving("Spotter") == ["h2m-sprite", "none"]                  # Spotter's lines: only Spotter talks
        assert moving("") == ["none", "h2m-sprite"]                         # the narrator's: only the narrator's character
        assert moving(None) == ["none", "none"]                             # silence: nobody
        b.close()


def _png(w=200, h=120):
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for x in range(w // 4, 3 * w // 4):
        for y in range(h // 4, 3 * h // 4): im.putpixel((x, y), (200, 30, 30, 255))
    buf = io.BytesIO(); im.save(buf, "PNG"); return buf.getvalue()


def _clip(tmp_path, seconds=3, speak=(1.0, 2.0)):
    """A small MP4 with a moving square and a tone (speech) between `speak` seconds."""
    out = tmp_path / "clip.mp4"
    a, b = speak
    subprocess.run([cli.FFMPEG, "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size=320x240:rate=24:duration={seconds}",
                    "-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds}", "-af", f"volume='between(t,{a},{b})':eval=frame",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)], check=True)
    return out.read_bytes()


def test_a_clip_is_kept_as_webm_knows_when_it_speaks_and_plays_on_a_slide(tmp_path):
    it = media.add(_clip(tmp_path), "Hello clip.mp4")
    assert it["format"] == "webm" and it["name"] == "Hello clip" and it["w"] == 320 and 2.8 < it["seconds"] < 3.2
    assert len(it["speech"]) == 1 and abs(it["speech"][0][0] - 1.0) < 0.15 and abs(it["speech"][0][1] - 2.0) < 0.15
    assert media.image(it).size == (320, 240) and media.thumb(it)[1] == "image/webp"                  # its picture is a poster frame
    assert media.export(it, "webm")[1] == "video/webm" and media.export(it, "png")[1] == "image/png"
    with pytest.raises(media.MediaError, match="video clip can have"): media.edit(it["id"], "crop", {"box": [0, 0, 0.5, 0.5]})
    assert "video clip, 3 s" in media.catalog_text() or "video clip, 3.0" in media.catalog_text() or "video clip" in media.catalog_text()
    html, missing = media.resolve(f'<img data-asset="{it["id"]}" alt="Our hello" class="clip" data-c="0">')
    assert not missing and html.startswith("<video") and "data-h2m-video" in html and "muted" in html and 'data-c="0"' in html and "data:video/webm;base64," in html
    m = script.parse("Title: T\n## A\nSay: One sentence that runs a while here.\n## B\nSay: Two.\n")
    f = tmp_path / "m.html"; f.write_text(compose.assemble(m, config.brand(), [("custom", '<h2 data-c="0">A</h2>' + html), ("custom", '<h2 data-c="0">B</h2>')]))
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(); pg.goto(f.as_uri())
        pg.evaluate(cli.PAGE_JS, ["s1", "s2"]); pg.evaluate("__html2mp4.reset()")
        pg.evaluate("__html2mp4.show(0, 0, 5.0)")                           # the slide appears 5 s into the video
        at = lambda t: pg.evaluate(f"__html2mp4.frame({t}, null).then(() => document.querySelector('#s1 video').currentTime)")
        assert at(5.0) == pytest.approx(0, abs=0.01) and at(6.5) == pytest.approx(1.5, abs=0.01) and at(5.25) == pytest.approx(0.25, abs=0.01)
        assert at(30) == pytest.approx(it["seconds"], abs=0.05)              # then it holds its last picture
        b.close()


def test_a_clip_of_a_character_speaking_becomes_a_talking_character(tmp_path):
    frames = []                                                          # a transparent clip: a disc whose "mouth" opens in the middle second
    for k in range(36):
        im = Image.new("RGBA", (160, 160), (0, 0, 0, 0)); a = np.zeros((160, 160, 4), np.uint8)
        yy, xx = np.mgrid[:160, :160]; a[(yy - 80) ** 2 + (xx - 80) ** 2 < 60 ** 2] = (240, 200, 60, 255)
        if 12 <= k < 24: a[(yy - 105) ** 2 / 9 + (xx - 80) ** 2 / 400 < 1 + (k % 4)] = (60, 20, 20, 255)
        frames.append(Image.fromarray(a, "RGBA"))
    data, w, h = media._encode_webm(frames, 12, True)
    src = media._store(data, "webm", w, h, True, "Disc", "mascot", "", None, "test", None, {"seconds": 3.0, "fps": 12, "speech": [[1.0, 2.0]], "poster": 0})
    assert media.video_frames(src, 0, 0.1, 12)[0].mode == "RGBA" and media.video_frames(src, 0, 0.1, 12)[0].getchannel("A").getextrema()[0] == 0
    ch = media.edit(src["id"], "character", {"speaker": "Disc", "frames": 6})
    assert ch["animated"] == {"frames": 10, "fps": 12, "mode": "character", "rows": 2} and ch["speaker"] == "Disc" and ch["transparent"]
    idle, talk = media.frames(ch, 0), media.frames(ch, 1)
    dark = lambda f: int(((np.asarray(f)[..., :3].astype(int).sum(2) < 300) & (np.asarray(f)[..., 3] > 128)).sum())
    assert max(map(dark, idle)) < 20 < min(map(dark, talk))                  # the idle loop is from the quiet part, the talking one from the speech
    assert np.abs(np.asarray(idle[1]).astype(int) - np.asarray(idle[-1]).astype(int)).sum() == 0 or len(idle) == 10   # forward then back
    with pytest.raises(media.MediaError, match="no speech"):
        media.edit(media._store(data, "webm", w, h, True, "Mute", "mascot", "", None, "t", None, {"seconds": 3.0, "fps": 12, "speech": []})["id"], "character", {})


def test_the_studio_takes_clips_and_a_speaker(client, tmp_path):
    r = client.post("/api/media", files=[("files", ("Hello.mp4", _clip(tmp_path), "video/mp4"))]).json()
    it = r["items"][0]
    assert it["video"] and it["format"] == "webm" and client.get(f"/api/media/{it['id']}/file").headers["content-type"] == "video/webm"
    assert client.get(f"/api/media/{it['id']}/preview").headers["content-type"] == "image/webp"
    still = client.post("/api/media", files=[("files", ("Face.png", _png(), "image/png"))]).json()["items"][0]
    assert client.patch(f"/api/media/{still['id']}", json={"speaker": "Spotter"}).json()["speaker"] == "Spotter"
    assert "speaker" not in client.patch(f"/api/media/{still['id']}", json={"speaker": ""}).json()


def test_a_subject_on_a_plain_backdrop_is_found_without_a_box():
    im = Image.new("RGB", (300, 200), (250, 250, 250))
    a = np.asarray(im).copy(); a[40:200, 100:200] = (40, 120, 200); im = Image.fromarray(a)     # touches the bottom edge, like a cropped character
    box = media.subject_box(im)
    assert box and box[0] == pytest.approx(100 / 300, abs=0.03) and box[2] == pytest.approx(200 / 300, abs=0.03) and box[3] == 1
    noisy = Image.fromarray(np.random.default_rng(1).integers(0, 255, (200, 300, 3), dtype=np.uint8))
    assert media.subject_box(noisy) is None                                # a busy photo: nothing to tell from the backdrop
    rgba = Image.new("RGBA", (100, 100), (0, 0, 0, 0)); rgba.paste((9, 9, 9, 255), (20, 30, 60, 90))
    assert media.subject_box(rgba) == [0.2, 0.3, 0.6, 0.9]


def test_the_assistant_and_the_designer_know_about_speakers_and_clips():
    from html2mp4 import chat
    assert "Voice: NAME = VOICE" in chat.SYSTEM and "character" in json.dumps(chat.SCHEMA) and "Video clips" in chat.SYSTEM
    assert "(NAME speaks)" in design.SYSTEM and "video clip" in design.SYSTEM


def test_a_library_image_keeps_the_designers_class_whatever_quotes_it_used():
    talker = media.edit(media.add(_png(), "Spot.png")["id"], "talk", {"mouth": [0.3, 0.5, 0.7, 0.7]}, name="Spot (talking)")
    html, _ = media.resolve(f"<img data-asset='{talker['id']}' alt='Spot waves' class='s1-dog big' style='width:30%' data-c='0'>")
    assert html.count("class=") == 1 and 'class="h2m-sprite h2m-talk s1-dog big"' in html and html.count("style=") == 1 and "width:30%" in html
    assert 'aria-label="Spot waves"' in html and "data-c='0'" in html
    still = media.add(_png(), "Logo.png")
    html, _ = media.resolve(f"<img class='lg' data-asset='{still['id']}' alt='Our logo'>")
    assert html.count("class=") == 1 and 'alt="Our logo"' in html
