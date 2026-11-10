import re
import time
import pytest
from fastapi.testclient import TestClient
from html2mp4 import config, projects, script, studio


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "config" / "settings.json")
    monkeypatch.setattr(projects, "MODULES", tmp_path / "modules")
    monkeypatch.setattr(studio, "UPLOADS", tmp_path / "uploads")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    studio.design_jobs.clear()
    return TestClient(studio.app)


def wait(client, job, seconds=120):
    end = time.time() + seconds
    while time.time() < end:
        j = client.get(f"/api/write/jobs/{job['id']}").json()
        if j["status"] in ("done", "failed"): return j
        time.sleep(0.5)
    raise AssertionError("job did not finish")


def test_parse_and_errors(client):
    ok = client.post("/api/write/parse", json={"script": script.EXAMPLE}).json()
    assert ok["title"] == "Giving Feedback That Lands" and len(ok["slides"]) == 3 and ok["sentences"] == 7
    assert [s["id"] for s in ok["slides"]] == ["s1", "s2", "s3"]
    bad = client.post("/api/write/parse", json={"script": "Title: T"})
    assert bad.status_code == 422 and "no slides" in bad.json()["detail"]


def test_designing_needs_a_key_but_quick_layout_does_not(client):
    r = client.post("/api/write/generate", json={"script": script.EXAMPLE, "mode": "design"})
    assert r.status_code == 400 and "API key" in r.json()["detail"]
    assert client.post("/api/write/review", json={"script": script.EXAMPLE}).status_code == 400


def test_quick_layout_to_video_handoff(client):
    r = client.post("/api/write/generate", json={"script": script.EXAMPLE, "mode": "basic"}).json()
    pid = r["project"]
    assert wait(client, r["job"])["status"] == "done"
    p = client.get(f"/api/projects/{pid}").json()
    assert p["current"] == 1 and p["versions"][0]["mode"] == "basic" and [i for i in p["issues"] if i["severity"] == "error"] == []
    assert p["outline"]["slides"][0]["title"] == "Why feedback matters"
    page = client.get(f"/api/projects/{pid}/module.html")
    assert page.status_code == 200 and "Giving Feedback That Lands" in page.text and page.headers["cache-control"] == "no-store"
    up = client.post(f"/api/projects/{pid}/to-video").json()
    assert up["title"] == "Giving Feedback That Lands" and len(up["scenes"]) == 4 and up["project"] == pid
    assert client.get("/api/projects").json()[0]["id"] == pid
    assert client.delete(f"/api/projects/{pid}").json() == {"ok": True} and client.get("/api/projects").json() == []


def test_editing_a_quick_layout_script_makes_a_new_version(client):
    r = client.post("/api/write/generate", json={"script": script.EXAMPLE, "mode": "basic"}).json()
    wait(client, r["job"])
    edited = script.EXAMPLE.replace("Feedback is how good teams get better.", "Feedback is how teams improve.")
    u = client.put(f"/api/projects/{r['project']}/script", json={"script": edited}).json()
    assert u["changed"] == ["s1"] and wait(client, u["job"])["status"] == "done"
    p = client.get(f"/api/projects/{r['project']}").json()
    assert p["current"] == 2 and "teams improve" in p["script"]
    assert client.put(f"/api/projects/{r['project']}/script", json={"script": edited}).json()["job"] is None     # nothing changed


def test_which_slides_an_edit_touches():
    new = script.EXAMPLE.replace("Your next step", "Your first step")
    assert studio.changed_slides(script.EXAMPLE, new) == ["s3"]
    assert studio.changed_slides(script.EXAMPLE, script.EXAMPLE + "\n## Extra\nSay: More.") == ["s4"]


def test_moment_note_maps_times_to_slides():
    note = studio.moment_note(script.parse(script.EXAMPLE))
    assert "s1 (Why feedback matters) starts at about 0:00" in note and "s3 (Your next step)" in note


def test_glossary_endpoints(client):
    assert client.put("/api/settings/glossary", json={"pronunciations": {"R&D": "R and D"}, "banned": ["Old"]}).json()["banned"] == ["Old"]
    assert client.get("/api/settings/glossary").json()["pronunciations"] == {"R&D": "R and D"}


def test_script_edit_note_names_slides_and_old_narration():
    new = script.EXAMPLE.replace("Feedback is how good teams get better.", "Feedback is how teams improve.")
    note = studio.edit_note(script.EXAMPLE, new, ["s1"])
    assert "update the design of s1" in note and "0: Feedback is how good teams get better." in note
    assert studio.edit_note(script.EXAMPLE, new, []) == ""
    assert "s4 is a new slide" in studio.edit_note(script.EXAMPLE, script.EXAMPLE + "\n## Extra\nSay: More.", ["s4"])


def test_earlier_feedback_is_carried_into_later_changes():
    p = {"feedback": [{"text": "remove the HR line", "scope": ["s6"]}, {"text": "use larger cards", "scope": "all"},
                      {"text": "unrelated to s2", "scope": ["s3"]}, {"text": "the new request", "scope": ["s6"]}]}
    note = studio.history_note(p, ["s6"], "the new request")
    assert "remove the HR line (slides s6)" in note and "use larger cards" in note
    assert "unrelated to s2" not in note and "the new request" not in note
    assert studio.history_note({"feedback": []}, None, "x") == ""


def test_design_quality_endpoint(client):
    assert client.get("/api/settings").json()["design_quality"] == "balanced"
    assert client.put("/api/settings/design-quality", json={"value": "thorough"}).json() == {"design_quality": "thorough"}
    assert client.get("/api/settings").json()["design_quality"] == "thorough"
    assert client.put("/api/settings/design-quality", json={"value": "x"}).status_code == 400


def test_phase_and_eta_follow_the_stage_a_design_is_in():
    assert studio.phase_of("Designing the slides: planning the layouts") == "plan"
    assert studio.phase_of("Designing the slides (3 of 6 written)") == "write"
    assert studio.phase_of("Checking every slide, step by step") == "check"
    assert studio.phase_of("Fixing the slides (1 of 2 fixed)") == "fix"
    assert studio.eta_for({"phase": "plan", "label": "x"}) is None                    # nothing measurable while Claude plans: no invented number
    assert studio.eta_for({"phase": "write", "label": "Designing the slides (2 of 6 written)"}) == 4 * 12 + 90
    assert studio.eta_for({"phase": "review", "label": "Reviewing the design"}) == 30


def test_a_design_job_exposes_activity_and_live_thoughts(client):
    job = studio.design_jobs["j"] = {"id": "j", "project": "p", "status": "running", "progress": 0.3, "label": "Designing the slides (2 of 6 written)",
                                     "phase": "write", "created": 0, "started": 0, "activity": [{"t": 1, "kind": "plan", "text": "hello"}] * 100,
                                     "thoughts": {"a": {"label": "slides 1–2", "text": "weighing the heading", "at": 2}, "b": {"label": "slide 3", "text": "", "at": 1}}}
    j = client.get("/api/write/jobs/j").json()
    assert len(j["activity"]) == 80 and j["phase"] == "write" and j["eta"] == 4 * 12 + 90
    assert [t["label"] for t in j["thoughts"]] == ["slide 3", "slides 1–2"]


def _designed_project(client, title_script=None):
    """A project with a quick-layout version (no AI needed)."""
    r = client.post("/api/write/generate", json={"script": title_script or script.EXAMPLE, "mode": "basic"}).json()
    wait(client, r["job"]); return r["project"]


def test_motion_setting(client):
    assert client.get("/api/settings").json()["motion"] == "lively"
    assert client.put("/api/settings/motion", json={"value": "calm"}).json() == {"motion": "calm"}
    assert client.put("/api/settings/motion", json={"value": "wild"}).status_code == 400
    pid = _designed_project(client)
    assert 'data-motion="calm"' in client.get(f"/api/projects/{pid}/module.html").text


def test_download_is_a_single_attachment(client, monkeypatch):
    pid = _designed_project(client)
    monkeypatch.setattr(studio.compose, "embed_fonts", lambda page: page + "<!--fonts-->")
    r = client.get(f"/api/projects/{pid}/download")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"] and ".html" in r.headers["content-disposition"]
    assert r.text.endswith("<!--fonts-->") and "speechSynthesis" in r.text


def test_a_downloaded_module_comes_back_as_an_editable_project(client):
    pid = _designed_project(client)
    page = client.get(f"/api/projects/{pid}/module.html").text
    r = client.post("/api/projects/import", files={"file": ("m.html", page.encode(), "text/html")})
    assert r.status_code == 200, r.text
    got = r.json(); assert got["edited"] is False and got["title"] == "Giving Feedback That Lands" and got["project"] != pid
    view = client.get(f"/api/projects/{got['project']}").json()
    assert view["script"] == script.EXAMPLE and view["versions"][0]["note"] == "Imported from a file" and view["versions"][0]["mode"] == "basic"
    assert client.get(f"/api/projects/{got['project']}/module.html").text == page


def test_importing_a_changed_file_says_so_and_a_foreign_file_is_refused(client):
    pid = _designed_project(client)
    page = client.get(f"/api/projects/{pid}/module.html").text
    changed = client.post("/api/projects/import", files={"file": ("m.html", page.replace("Welcome", "Hello", 1).encode(), "text/html")}).json()
    assert changed["edited"] is True
    assert "changed outside" in client.get(f"/api/projects/{changed['project']}").json()["versions"][0]["note"]
    foreign = client.post("/api/projects/import", files={"file": ("x.html", b"<html><body>hi</body></html>", "text/html")})
    assert foreign.status_code == 422 and "Create video" in foreign.json()["detail"]


def test_import_adds_only_missing_pronunciations(client):
    config.set_glossary({"pronunciations": {"R&D": "R and D"}})
    pid = _designed_project(client)
    page = client.get(f"/api/projects/{pid}/module.html").text
    import json as _j, re as _re
    data = compose_project(page); data["pronunciations"] = {"R&D": "are and dee", "SQL": "sequel"}
    page = studio.compose.PROJECT_RE.sub(lambda m: m.group(1) + _j.dumps(data) + m.group(3), page)
    r = client.post("/api/projects/import", files={"file": ("m.html", page.encode(), "text/html")}).json()
    assert r["pronunciations_added"] == 1
    assert config.glossary()["pronunciations"] == {"R&D": "R and D", "SQL": "sequel"}               # nothing overwritten


def compose_project(page): return studio.compose.read_project(page)


def _fake_voice(monkeypatch, tmp_path, calls=None, slow=0.0):
    import numpy as np, soundfile as sf
    monkeypatch.setattr(studio.cli, "CACHE", tmp_path / "cache")
    def fake_synth(scenes, voice, speed, cache, progress=lambda f: None, pronounce=None, timings=False, status=None):
        cache.mkdir(parents=True, exist_ok=True)
        if status: status("waiting"); time.sleep(slow); status("loading")
        todo = [c for sc in scenes for c in sc["chunks"]]
        for i, c in enumerate(todo):
            progress(i / len(todo)); time.sleep(slow)
            f = studio.cli.clip_path(c, voice, speed, cache, pronounce)
            sf.write(f, np.zeros(2400, dtype="float32"), 24000); f.with_suffix(".json").write_text('[["hello", 0.1]]')
        if calls is not None: calls.append(len(todo))
    monkeypatch.setattr(studio.cli, "synthesize", fake_synth)


def _poll(client, jid, labels=None, seconds=20):
    end = time.time() + seconds
    while time.time() < end:
        st = client.get(f"/api/narration/{jid}").json()
        if labels is not None: labels.append(st["label"])
        if st["status"] != "running": return st
        time.sleep(0.02)
    raise AssertionError("voice job did not finish")


def test_studio_voice_reports_honest_progress_then_serves_stateless_audio(client, monkeypatch, tmp_path):
    pid = _designed_project(client)
    _fake_voice(monkeypatch, tmp_path, slow=0.03)
    start = client.post(f"/api/projects/{pid}/narration").json()
    assert start["ready"] is None and start["id"]
    labels = []; st = _poll(client, start["id"], labels)
    assert st["status"] == "done" and st["times"][0][0] == [["hello", 0.1]]
    assert any("Waiting for another voice job" in l for l in labels) and any(l.startswith("Making the voice: sentence") for l in labels)
    assert st["total"] == st["done"] or st["done"] >= st["total"] - 1
    audio = client.get(st["urls"][0][0])
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/wav" and len(audio.content) > 2000
    assert client.get(f"/api/projects/{pid}/narration/audio/9/9").status_code == 404


def test_audio_addresses_survive_a_studio_restart_and_cached_voice_is_instant(client, monkeypatch, tmp_path):
    pid = _designed_project(client)
    made = []; _fake_voice(monkeypatch, tmp_path, calls=made)
    st = _poll(client, client.post(f"/api/projects/{pid}/narration").json()["id"])
    studio.narrations.clear()                                                   # what a restart does: every running job is forgotten
    assert client.get(st["urls"][1][0]).status_code == 200                     # the audio address still works
    again = client.post(f"/api/projects/{pid}/narration").json()
    assert again["id"] is None and again["ready"]["status"] == "done" and len(made) == 1       # nothing was made twice
    stale = client.get("/api/narration/gone")
    assert stale.status_code == 404 and "Press Studio voice again" in stale.json()["detail"]


def test_an_unvoiced_sentence_is_not_found_rather_than_an_error(client, monkeypatch, tmp_path):
    pid = _designed_project(client)
    monkeypatch.setattr(studio.cli, "CACHE", tmp_path / "empty-cache")
    r = client.get(f"/api/projects/{pid}/narration/audio/0/0")
    assert r.status_code == 404 and "hasn't been voiced" in r.json()["detail"]


def test_old_modules_are_served_with_the_current_player(client):
    pid = _designed_project(client)
    old = (__import__("pathlib").Path(__file__).parent / "fixtures" / "module_player_v1.html").read_text()
    (projects.folder(pid) / "versions" / "v1.html").write_text(old, encoding="utf-8")
    served = client.get(f"/api/projects/{pid}/module.html").text
    assert 'id="studiovoice"' in served and "h2m:player-js" in served and served.count('id="bar"') == 1
    assert 'id="studiovoice"' in client.get(f"/api/projects/{pid}/download").text


def test_inserting_or_removing_a_slide_keeps_the_designs_of_the_others():
    base = script.EXAMPLE
    mid = base.replace("## The SBI model", "## A new idea\nSay: Something new.\n\n## The SBI model")
    remap, changed = studio.align_slides(base, mid)
    assert changed == ["s2"] and remap == {"s1": "s1", "s3": "s2", "s4": "s3"}
    assert studio.changed_slides(base, mid) == ["s2"]
    remap, changed = studio.align_slides(mid, base)                                  # and removing it again
    assert changed == [] and remap == {"s1": "s1", "s2": "s3", "s3": "s4"}
    remap, changed = studio.align_slides(base, base.replace("Feedback is how good teams get better.", "Feedback helps teams grow."))
    assert changed == ["s1"] and remap["s1"] == "s1"                                  # an edited slide starts from its old design


def test_a_moved_design_follows_its_slide_id():
    d = {"layout": "cards", "summary": "x", "html": '<svg><defs><linearGradient id="s3-g"/></defs><path fill="url(#s3-g)"/></svg><div class="s3-box"><i class="x s3-vs"></i></div><p>s3 buckets</p>', "css": "#s3 .a{color:red}\n#s3 .s3-box{margin:0}\n#s3-g{opacity:1}"}
    moved = studio.remap_design(d, "s3", "s5")
    assert moved["css"] == "#s5 .a{color:red}\n#s5 .s3-box{margin:0}\n#s5-g{opacity:1}" and 'id="s5-g"' in moved["html"] and "url(#s5-g)" in moved["html"]
    assert 'class="s3-box"' in moved["html"] and 'class="x s3-vs"' in moved["html"] and "<p>s3 buckets</p>" in moved["html"]      # class names stay as they are
    assert moved["layout"] == "cards" and studio.remap_design(d, "s3", "s3") == d


def test_apply_runs_one_design_for_a_script_edit_and_visual_requests_together(client, monkeypatch):
    from test_design import FakeClaude
    from html2mp4 import ai
    config.set_api_key("sk-ant-test-key-1234567890")
    monkeypatch.setattr(ai, "structured", FakeClaude())
    r = client.post("/api/write/generate", json={"script": script.EXAMPLE, "mode": "design"}).json()
    assert wait(client, r["job"], 240)["status"] == "done"
    pid = r["project"]; before = projects.slides(pid)
    fake = FakeClaude(); monkeypatch.setattr(ai, "structured", fake)
    mid = script.EXAMPLE.replace("## The SBI model", "## A new idea\nShow: One · Two\nSay: Something new.\n\n## The SBI model")
    out = client.post(f"/api/projects/{pid}/apply", json={"script": mid, "requests": [{"slides": ["s3", "s99"], "request": "make it a flow"}]}).json()
    assert out["changed"] == ["s2"] and wait(client, out["job"], 240)["status"] == "done"
    sent = fake.of("revise")
    assert sorted(re.search(r"from: ([^.]*)\.", r["text"]).group(1) for r in sent) == ["s2", "s3"]      # side by side, one call per slide
    assert all("make it a flow" in r["text"] and "Visual changes" in r["text"] for r in sent)
    assert not fake.of("design")                                                   # nothing else was designed
    after = projects.slides(pid)
    assert after["s1"] == before["s1"] and after["s4"]["html"] == before["s3"]["html"]      # the slide after the insert kept its design
    p = client.get(f"/api/projects/{pid}").json()
    assert p["current"] == 2 and p["versions"][-1]["note"].startswith("Assistant: script edited (1 slide) and 1 visual change") and "A new idea" in p["script"]
    # a visual request alone leaves the script alone and touches only the slide it names
    fake2 = FakeClaude(); monkeypatch.setattr(ai, "structured", fake2)
    out = client.post(f"/api/projects/{pid}/apply", json={"requests": [{"slides": ["s1"], "request": "bigger title"}]}).json()
    assert out["changed"] == [] and wait(client, out["job"], 240)["status"] == "done" and re.search(r"from: s1\.", fake2.of("revise")[0]["text"])
    assert client.post(f"/api/projects/{pid}/apply", json={}).json() == {"job": None, "changed": []}


def test_apply_refuses_visual_changes_on_a_quick_layout(client):
    config.set_api_key("sk-ant-test-key-1234567890")
    r = client.post("/api/write/generate", json={"script": script.EXAMPLE, "mode": "basic"}).json(); wait(client, r["job"])
    bad = client.post(f"/api/projects/{r['project']}/apply", json={"requests": [{"slides": ["s1"], "request": "bigger"}]})
    assert bad.status_code == 400 and "Design with Claude" in bad.json()["detail"]
    assert client.post("/api/projects/nope/apply", json={}).status_code == 404
