"""The media library: uploading, cleaning, editing, using images on slides, and the assistant working with them."""
import io, json, re
import pytest
from PIL import Image
from html2mp4 import compose, config, design, media, script, verify
from test_studio import client, wait   # noqa: F401


def png(w=200, h=120, color=(200, 30, 30), alpha=True):
    im = Image.new("RGBA" if alpha else "RGB", (w, h), (0, 0, 0, 0) if alpha else (255, 255, 255))
    for x in range(w // 4, 3 * w // 4):
        for y in range(h // 4, 3 * h // 4): im.putpixel((x, y), color + ((255,) if alpha else ()))
    buf = io.BytesIO(); im.save(buf, "PNG"); return buf.getvalue()


def jpeg_with_gps():
    im = Image.new("RGB", (3000, 2000), (40, 90, 160)); exif = Image.Exif(); exif[0x8825] = {2: (37.0, 25.0, 1.0)}; exif[0x010F] = "PhoneCo"
    buf = io.BytesIO(); im.save(buf, "JPEG", exif=exif.tobytes()); return buf.getvalue()


def test_upload_cleans_the_image():
    it = media.add(jpeg_with_gps(), "Bangalore office.jpg")
    assert it["name"] == "Bangalore office" and it["kind"] == "photo" and it["format"] == "jpg" and max(it["w"], it["h"]) == media.MAX_SIDE
    assert not Image.open(media.path(it)).getexif()                                    # the GPS location and camera details are gone
    cut = media.add(png(), "logo.png")
    assert cut["transparent"] and cut["format"] == "png" and cut["kind"] == "icon"
    assert media.add(png(), "logo.png")["name"] == "logo (2)" and media.get("LOGO")["id"] == "logo"   # names stay unique; found by name too
    with pytest.raises(media.MediaError, match="isn't an image"): media.add(b"hello", "x.png")
    with pytest.raises(media.MediaError, match="scripts"): media.add(b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>', "x.svg")
    svg = media.add(b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 32"><rect width="64" height="32" fill="red"/></svg>', "badge.svg")
    assert (svg["format"], svg["w"], svg["h"]) == ("svg", 64, 32)


def test_an_animated_gif_becomes_frames_a_slide_can_step_through():
    frames = [Image.new("RGBA", (40, 30), (k * 60, 0, 0, 255)) for k in range(4)]
    buf = io.BytesIO(); frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
    it = media.add(buf.getvalue(), "spinner.gif")
    assert it["animated"] == {"frames": 4, "fps": 10, "mode": "loop"} and it["format"] == "webp" and (it["w"], it["h"]) == (40, 30)
    gif, mime = media.export(it, "gif"); assert mime == "image/gif" and Image.open(io.BytesIO(gif)).n_frames == 4


def test_edits_make_new_images_and_keep_the_original():
    src = media.add(png(400, 200), "Badge.png")
    crop = media.edit(src["id"], "crop", {"box": [0.25, 0.25, 0.75, 0.75]})
    assert (crop["w"], crop["h"]) == (200, 100) and crop["parent"] == src["id"] and crop["name"] == "Badge (cropped)"
    trim = media.edit(src["id"], "trim"); assert (trim["w"], trim["h"]) == (200, 100)
    sq = media.edit(trim["id"], "pad"); assert sq["w"] == sq["h"]
    rot = media.edit(src["id"], "rotate", {"degrees": 90}); assert (rot["w"], rot["h"]) == (200, 400)
    jpg = media.edit(src["id"], "convert", {"format": "jpg"}); assert jpg["format"] == "jpg" and not jpg["transparent"]
    small = media.edit(src["id"], "resize", {"max": 100}); assert max(small["w"], small["h"]) == 100
    bob = media.edit(src["id"], "bob"); assert bob["animated"]["mode"] == "loop" and bob["animated"]["frames"] == 16
    assert media.get(src["id"])["w"] == 400 and len(media.listing()) == 8                  # the original is untouched
    for bad in ({"box": [0.5, 0.5, 0.5, 0.5]}, {"box": "x"}):
        with pytest.raises(media.MediaError): media.edit(src["id"], "crop", bad)
    with pytest.raises(media.MediaError, match="Unknown edit"): media.edit(src["id"], "recolour")


def test_a_talking_image_opens_its_mouth_below_the_line():
    im = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    for x in range(20, 80):
        for y in range(20, 90): im.putpixel((x, y), (240, 240, 240, 255))
    buf = io.BytesIO(); im.save(buf, "PNG"); src = media.add(buf.getvalue(), "Face.png")
    t = media.edit(src["id"], "talk", {"mouth": [0.3, 0.5, 0.7, 0.8], "open": 0.06})
    assert t["animated"]["mode"] == "talk" and t["animated"]["frames"] == 10
    fr = media.frames(t)
    assert fr[0].getpixel((50, 52))[:3] == (240, 240, 240)                                    # closed: as it was
    widest = fr[3].getpixel((50, 52))[:3]; assert widest[0] < 80                               # open: dark mouth just below the line
    assert fr[3].getpixel((50, 30))[:3] == (240, 240, 240) and fr[3].getpixel((25, 52))[:3] == (240, 240, 240)   # above it, and the corners, stay


def test_slides_carry_library_images_and_a_talker_moves_only_while_speaking():
    still = media.add(png(), "Logo.png")
    face = media.edit(media.add(png(), "Face.png")["id"], "talk", {"mouth": [0.3, 0.5, 0.7, 0.7]}, name="Face (talking)")
    html, missing = media.resolve(f'<img data-asset="{still["id"]}" class="lg" style="width:80px"><img data-asset="{face["id"]}" alt="Our host"><img data-asset="nope">')
    assert missing == ["nope"]
    assert re.search(r'<img class="lg" style="width:80px" src="data:image/png;base64,[^"]+" alt="Logo"', html)
    assert 'class="h2m-sprite h2m-talk"' in html and 'aria-label="Our host"' in html and "steps(10,jump-none)" in html and "background-size:1000% 100%" in html
    ok = verify.static_issues("s1", f'<img data-asset="{still["id"]}" alt="x">', "")
    bad = verify.static_issues("s1", '<img src="https://x.test/a.png">', "") + verify.static_issues("s1", '<img data-asset="a" src="data:x">', "")
    assert ok == [] and len(bad) >= 2


def test_the_designer_is_told_about_the_library_and_unknown_images_are_caught():
    it = media.add(png(), "Spotter.png"); media.update(it["id"], kind="mascot", description="Our mascot")
    assert "spotter: “Spotter” (mascot" in media.catalog_text() and "Our mascot" in media.catalog_text()
    m = script.parse("Title: T\n## A\nImage: Spotter\nSay: Hello there.\n")
    assert m.slides[0].images == ["Spotter"] and "Show these images from the media library: Spotter" in design._scenes_text(m, ["s1"])
    slides = {"s1": {"layout": "x", "summary": "x", "html": '<h2 class="t-heading" data-c="0">Hello</h2><img data-asset="ghost" alt="x">', "css": ""}}
    _, issues, _ = design._check(m, config.brand(), slides, [], "calm", None, {})
    assert any("isn't in the media library" in i.message for i in issues)


def test_the_studio_endpoints(client):
    r = client.post("/api/media", files=[("files", ("Spotter.png", png(), "image/png")), ("files", ("bad.txt", b"no", "text/plain"))]).json()
    assert len(r["items"]) == 1 and r["errors"] and r["items"][0]["preview"].endswith("/preview")
    iid = r["items"][0]["id"]
    assert client.get(f"/api/media/{iid}/file").headers["content-type"] == "image/png"
    d = client.get(f"/api/media/{iid}/download", params={"format": "gif"})
    assert d.headers["content-type"] == "image/gif" and "Spotter.gif" in d.headers["content-disposition"]
    assert client.patch(f"/api/media/{iid}", json={"name": "Spotter dog", "kind": "mascot"}).json()["kind"] == "mascot"
    assert client.patch(f"/api/media/{iid}", json={"kind": "wizard"}).status_code == 400
    job = client.post(f"/api/media/{iid}/edit", json={"op": "crop", "params": {"box": [0, 0, 0.5, 0.5]}}).json()
    import time
    for _ in range(50):
        j = client.get(f"/api/media/jobs/{job['id']}").json()
        if j["status"] != "running": break
        time.sleep(0.1)
    assert j["status"] == "done" and j["item"]["name"] == "Spotter dog (cropped)"
    assert client.post(f"/api/media/{iid}/edit", json={"op": "talk", "params": {}}).status_code == 400           # needs Claude to find the mouth
    assert client.get("/api/media").json()["kinds"] == list(media.KINDS)
    assert client.delete(f"/api/media/{iid}").json() == {"ok": True} and client.get(f"/api/media/{iid}/file").status_code == 404


class Look:
    """Stands in for Claude looking at an image."""
    def __init__(self, answers): self.answers, self.seen = list(answers), []
    def __call__(self, system, content, schema, **kw):
        self.seen.append(content)
        class U: input_tokens, output_tokens = 100, 50
        return self.answers.pop(0), U()


def test_claude_finds_the_mouth_and_looks_closer_to_be_precise():
    src = media.add(png(200, 200), "Face.png")
    look = Look([{"found": True, "box": [0.4, 0.4, 0.6, 0.6], "line": None, "note": ""},
                 {"found": True, "box": [0.25, 0.25, 0.75, 0.75], "line": [[0.25, 0.25], [0.75, 0.25]], "note": ""}])
    r, cost = media.locate(src["id"], "mouth", call=look)
    assert len(look.seen) == 2 and look.seen[1][0]["type"] == "image"                         # a second, closer look
    # the close-up covered [0.28, 0.28, 0.72, 0.72]; its answer maps back onto the whole image
    assert r["box"] == pytest.approx([0.39, 0.39, 0.61, 0.61], abs=0.002) and r["line"][0] == pytest.approx([0.39, 0.39], abs=0.002)
    with pytest.raises(media.MediaError, match="couldn't find"): media.locate(src["id"], "mouth", call=Look([{"found": False, "box": [], "line": None, "note": "no face"}]))
    d, _ = media.describe(src["id"], call=Look([{"name": "Red square", "kind": "icon", "description": "A red square.", "subject": [0.25, 0.25, 0.75, 0.75]}]))
    assert d["description"] == "A red square." and d["subject"] == [0.25, 0.25, 0.75, 0.75] and d["suggested"]["name"] == "Red square"


def test_the_assistant_can_see_attachments_and_edit_images(client, monkeypatch):
    from html2mp4 import ai, studio
    config.set_api_key("sk-ant-test-key-1234567890")
    up = client.post("/api/media", files=[("files", ("Banner.png", png(300, 200), "image/png"))]).json()["items"][0]
    seen = {}
    def fake(system, content, schema, **kw):
        last = kw["messages"][-1]["content"]; seen["blocks"] = last
        class U: input_tokens, output_tokens = 100, 50
        return {"reply": "Cut it out and made it square.", "script": None, "edits": [], "summary": [], "visual_requests": [], "suggestions": [],
                "image_ops": [{"asset": up["id"], "op": "crop", "box": [0.25, 0.25, 0.75, 0.75], "size": None, "degrees": None, "direction": None, "format": None, "name": "Banner subject", "kind": "mascot"},
                              {"asset": "previous", "op": "pad", "box": None, "size": None, "degrees": None, "direction": None, "format": None, "name": "Banner square", "kind": None},
                              {"asset": "ghost", "op": "trim", "box": None, "size": None, "degrees": None, "direction": None, "format": None, "name": None, "kind": None}]}, U()
    monkeypatch.setattr(ai, "structured", fake)
    job = client.post("/api/write/chat", json={"messages": [{"role": "user", "content": "cut out the dog"}], "attachments": [up["id"]]}).json()
    for _ in range(100):
        j = client.get(f"/api/write/chat/{job['id']}").json()
        if j["status"] != "running": break
        __import__("time").sleep(0.05)
    assert j["status"] == "done", j
    assert seen["blocks"][0]["type"] == "image" and "The media library" in seen["blocks"][-1]["text"] and up["id"] in seen["blocks"][-1]["text"]
    made = j["result"]["media"]
    assert made[0]["item"]["name"] == "Banner subject" and made[0]["item"]["kind"] == "mascot"
    assert made[1]["item"]["name"] == "Banner square" and made[1]["item"]["w"] == made[1]["item"]["h"]           # "previous" chained onto the crop
    assert "error" in made[2]


def test_a_module_with_an_image_reads_well_as_yaml_and_still_carries_it(client):
    from html2mp4 import projects
    it = media.add(png(), "Logo.png")
    p = projects.create("T", "Title: T\n## A\nSay: Hi.\n")
    page = compose.basic_module(script.parse("Title: T\n## A\nSay: Hi.\n"), config.brand(), motion="calm")
    page = page.replace("</section>", f'<img data-asset="{it["id"]}" alt="Logo"></section>', 1)
    projects.save_version(p["id"], media.resolve(page)[0], None, "Quick layout")
    view = client.get(f"/api/projects/{p['id']}/export", params={"format": "yaml", "inline": "true"}).text
    assert "<embedded image, " in view and "base64," not in view.split("<embedded image")[0][-200:]
    assert "data:image/png;base64," in client.get(f"/api/projects/{p['id']}/export").text      # the file itself keeps it


def critter():
    """A simple character: a body with a tail sticking up on the right and a mouth line, on a transparent background."""
    im = Image.new("RGBA", (200, 160), (0, 0, 0, 0))
    for x in range(40, 150):
        for y in range(60, 140): im.putpixel((x, y), (230, 230, 230, 255))
    for x in range(150, 170):
        for y in range(20, 80): im.putpixel((x, y), (200, 120, 60, 255))
    buf = io.BytesIO(); im.save(buf, "PNG"); return media.add(buf.getvalue(), "Critter.png")


def tail_mask(rgb, alpha, parts, W, H):
    import numpy as np
    m = np.zeros((H, W), np.float32)
    for p in parts:
        x0, y0, x1, y1 = round(p["box"][0] * W), round(p["box"][1] * H), round(p["box"][2] * W), round(p["box"][3] * H); m[y0:y1, x0:x1] = 1
    return [m * (alpha > 0.5)]


TAIL = {"name": "tail", "kind": "tail", "box": [150 / 200, 20 / 160, 170 / 200, 80 / 160], "joint": [160 / 200, 78 / 160], "tip": [160 / 200, 22 / 160]}
MOUTH = {"box": [0.3, 0.6, 0.6, 0.8], "line": [[0.3, 0.6], [0.6, 0.6]]}


def test_bringing_a_character_to_life_moves_its_parts_and_talks_on_a_second_row(monkeypatch):
    import numpy as np
    monkeypatch.setattr(media, "_part_masks", tail_mask)                       # the cut-out model is tested by hand; here, a known mask
    src = critter()
    it = media.edit(src["id"], "animate", {"parts": [TAIL], "mouth": MOUTH})
    assert it["animated"] == {"frames": 32, "fps": 16, "mode": "character", "rows": 2} and it["transparent"]
    idle, talk = media.frames(it, 0), media.frames(it, 1)
    tails = [np.asarray(f)[..., 3][: f.size[1] // 2, f.size[0] * 3 // 4:].sum() for f in idle]
    a0 = np.asarray(idle[0]).astype(int); a4 = np.asarray(idle[4]).astype(int)
    assert np.abs(a0 - a4)[: a0.shape[0] // 2, a0.shape[1] * 3 // 4:].sum() > 1000            # the tail is somewhere else
    assert np.abs(a0 - np.asarray(talk[0]).astype(int)).sum() < np.abs(a0 - np.asarray(talk[2]).astype(int)).sum()   # the mouth opens on the talking row
    html, _ = media.resolve(f'<img data-asset="{it["id"]}" alt="Critter">')
    assert 'class="h2m-sprite h2m-char"' in html and "background-size:3200% 200%" in html
    assert ".h2m-sprite.h2m-char:not([data-speaker])::after{opacity:1}" in media.SPRITE_CSS        # the talking row fades in over the idle one
    gif, _ = media.export(it, "gif", 1); assert Image.open(io.BytesIO(gif)).n_frames == 32
    with pytest.raises(media.MediaError, match="already animated"): media.edit(it["id"], "animate", {"parts": [TAIL]})
    with pytest.raises(media.MediaError, match="Remove the background first"): media.edit(media.add(png(alpha=False), "Photo.png")["id"], "animate", {"parts": [TAIL]})


def test_claude_finds_the_parts_and_the_mouth(monkeypatch):
    monkeypatch.setattr(media, "_part_masks", tail_mask)
    src = critter()
    look = Look([{"parts": [TAIL]}, {"found": True, "box": [0.3, 0.55, 0.6, 0.8], "line": None, "note": ""},
                 {"found": True, "box": [0.2, 0.2, 0.8, 0.8], "line": [[0.2, 0.2], [0.8, 0.2]], "note": ""}])
    it, cost = media.smart_edit(src["id"], "animate", {}, None, call=look)
    assert it["animated"]["mode"] == "character" and it["name"] == "Critter (animated)" and len(look.seen) == 3
    none = Look([{"parts": []}])
    with pytest.raises(media.MediaError, match="didn't find parts"): media.smart_edit(src["id"], "animate", {}, None, call=none)
    no_mouth = Look([{"parts": [TAIL]}, {"found": False, "box": [], "line": None, "note": "no mouth"}])
    it2, _ = media.smart_edit(src["id"], "animate", {}, "Tail only", call=no_mouth)
    assert it2["animated"]["mode"] == "loop" and it2["animated"]["rows"] == 1                 # it moves, but there's nothing to talk with
