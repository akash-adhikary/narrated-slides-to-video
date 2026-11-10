import json, re
import pytest
from test_studio import client, wait, _designed_project   # noqa: F401
from test_design import FakeClaude
from html2mp4 import ai, chat, cli, compose, config, projects, script

S = "Title: T\n## A\nShow: x · y\nHold: 3.5\nSay: One.\nSay: Two.\n## B\nSay: Three.\n"


def test_a_slide_can_say_how_long_it_stays_up():
    m = script.parse(S)
    assert [s.hold for s in m.slides] == [3.5, None]
    assert script.parse(S.replace("3.5", "2 seconds")).slides[0].hold == 2 and script.parse(S.replace("Hold: 3.5", "hold: 0")).slides[0].hold == 0
    for bad, msg in (("soon", "number of seconds"), ("31", "at most 30"), ("-1", "number of seconds"), ("", "number of seconds")):
        with pytest.raises(script.ScriptError, match=msg): script.parse(S.replace("3.5", bad))
    with pytest.raises(script.ScriptError, match="belongs under"): script.parse("Title: T\nHold: 2\n## A\nSay: x.\n")
    scenes = "Scene 1: Opening (0:00 to 0:30)\nHold: 4\nOnce upon a time. The end.\n"
    assert script.parse("A title\n" + scenes).slides[0].hold == 4                      # the Scene format too


def test_the_hold_reaches_the_page_and_the_video_reads_it_back():
    m = script.parse(S)
    page = compose.basic_module(m, config.brand(), motion="calm", script_text=S)
    assert "{id:'s1', hold:3.5, chunks:" in page and "{id:'s2', chunks:" in page
    scenes = cli.load_scenes(page)
    assert [s.get("hold") for s in scenes] == [3.5, None]                                # old pages (no hold) still read the same way
    old = page.replace("hold:3.5, ", "")
    assert all("hold" not in s for s in cli.load_scenes(old))


def audio(n): return __import__("numpy").zeros(int(cli.TTS_SR * n), dtype="float32")


def test_the_video_keeps_the_last_graphic_up_longer():
    scenes = [{"id": "s1", "chunks": ["a"]}, {"id": "s2", "chunks": ["b"], "hold": 4.0}, {"id": "s3", "chunks": ["c"]}]
    clips = [[audio(1)], [audio(1)], [audio(1)]]; spans = [{"0": 0.5}] * 3
    ev0, _, total0 = cli.build_timeline(scenes, clips, spans)
    ev1, _, total1 = cli.build_timeline(scenes, clips, spans, hold=1.5)
    start = lambda ev, si: [e[0] for e in ev if e[1] == si][0]
    stay = lambda ev, si: start(ev, si + 1) - start(ev, si)                       # how long slide si is up
    assert stay(ev1, 0) - stay(ev0, 0) == pytest.approx(1.5)                    # the setting adds time to a slide without its own Hold:
    assert stay(ev0, 1) - stay(ev0, 0) == pytest.approx(4.0) and stay(ev1, 1) == pytest.approx(stay(ev0, 1))   # a slide's own Hold: wins over the setting
    assert total1 - total0 == pytest.approx(1.5 + 0 + 1.5)                      # slide 1, slide 2 (own), and the last slide gets the setting too
    assert cli.build_timeline(scenes, clips, spans, hold=0.0)[2] == total0


def test_the_setting_is_validated_and_saved(client):
    assert client.get("/api/settings").json()["hold"] == "standard"
    assert client.put("/api/settings/hold", json={"value": "relaxed"}).json() == {"hold": "relaxed"} and config.hold_seconds() == 3.0
    assert client.put("/api/settings/hold", json={"value": "forever"}).status_code == 400 and config.hold() == "relaxed"


def test_the_page_a_viewer_gets_follows_the_setting_without_looking_edited(client):
    pid = _designed_project(client)
    plain = client.get(f"/api/projects/{pid}/module.html").text
    assert 'id="h2m-hold"' not in plain
    client.put("/api/settings/hold", json={"value": "comfortable"})
    held = client.get(f"/api/projects/{pid}/module.html").text
    assert "window.__h2mHold=1.5;" in held and held.count('id="h2m-hold"') == 1
    assert compose.fingerprint(held) == compose.fingerprint(plain) and compose.read_project(held)["edited"] is False   # not an edit
    assert "window.__h2mHold=1.5" in client.get(f"/api/projects/{pid}/download").text
    client.put("/api/settings/hold", json={"value": "standard"})
    assert 'id="h2m-hold"' not in client.get(f"/api/projects/{pid}/module.html").text


def play_gap(tmp_path, text, hold=0):
    """Seconds from the last sentence of slide 1 starting to slide 2's first sentence starting, in the real preview player."""
    from playwright.sync_api import sync_playwright
    m = script.parse(text)
    f = tmp_path / "p.html"; f.write_text(compose.with_hold(compose.basic_module(m, config.brand(), motion="calm", script_text=text), hold))
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(); pg.goto(f.as_uri())
        pg.evaluate("""() => { window.__t = {}; addEventListener('message', e => { if(e.data && e.data.html2mp4 === 'step' && !(e.data.pos in __t)) __t[e.data.pos] = performance.now(); }); }""")
        pg.click("#play")
        pg.wait_for_function("window.__t && window.__t[2] !== undefined", timeout=40000)
        t = pg.evaluate("__t"); b.close()
    return (t["2"] - t["1"]) / 1000


def test_the_preview_player_keeps_a_slide_up_by_the_hold(tmp_path):
    plain = play_gap(tmp_path, S.replace("Hold: 3.5\n", ""))
    held = play_gap(tmp_path, S.replace("Hold: 3.5\n", ""), hold=2)                    # the Studio's pacing setting
    own = play_gap(tmp_path, S.replace("Hold: 3.5", "Hold: 3"), hold=2)                 # the slide's own line wins over the setting
    assert held - plain == pytest.approx(2.0, abs=0.5) and own - plain == pytest.approx(3.0, abs=0.5)


def test_a_hold_only_edit_needs_no_claude_and_still_lands_in_the_page(client, monkeypatch):
    config.set_api_key("sk-ant-test-key-1234567890")
    fake = FakeClaude(); monkeypatch.setattr(ai, "structured", fake)
    r = client.post("/api/write/generate", json={"script": script.EXAMPLE, "mode": "design"}).json()
    assert wait(client, r["job"], 240)["status"] == "done"
    pid = r["project"]; designs = len(fake.requests)
    held = script.EXAMPLE.replace("## The SBI model\n", "## The SBI model\nHold: 3\n")
    boom = FakeClaude(); monkeypatch.setattr(ai, "structured", boom)
    out = client.post(f"/api/projects/{pid}/apply", json={"script": held}).json()
    assert out["changed"] == [] and out["job"] is not None and wait(client, out["job"], 240)["status"] == "done"
    assert not boom.requests                                                                          # timing only: Claude is not called
    v = client.get(f"/api/projects/{pid}").json()
    assert v["current"] == 2 and "Hold: 3" in v["script"] and v["versions"][-1]["note"].startswith("Assistant: timing")
    page = client.get(f"/api/projects/{pid}/module.html").text
    assert re.search(r"\{id:'s2', hold:3, chunks:", page)
    assert projects.slides(pid)["s2"] == projects.slides(pid, 1)["s2"]                                # the design is untouched
    # the same through the plain script update
    held2 = held.replace("Hold: 3", "Hold: 5")
    out = client.put(f"/api/projects/{pid}/script", json={"script": held2}).json()
    assert out["changed"] == [] and wait(client, out["job"], 240)["status"] == "done" and not boom.requests
    assert "hold:5, chunks" in client.get(f"/api/projects/{pid}/module.html").text


def test_the_assistant_knows_about_hold_and_the_chat_card_names_it():
    assert "`Hold:`" in chat.SYSTEM and "never put it in `visual_requests`" in chat.SYSTEM
    old = S.replace("Hold: 3.5\n", ""); new = S
    assert chat.diff(old, new) == [{"slide": "s1", "title": "A", "kind": "timing"}]
    assert chat.diff(S, S) == []
