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
