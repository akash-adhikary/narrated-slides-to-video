import json, re
import pytest
from test_studio import client, wait, _designed_project   # noqa: F401
from test_design import FakeClaude, slide
from html2mp4 import ai, config, modulefile, projects, script

ORIG = slide("s1", '<h2 class="t-heading" data-c="0">ORIGINAL ONE</h2>')
NEW = slide("s1", '<h2 class="t-heading" data-c="0">REWRITTEN ONE</h2>')


@pytest.fixture
def designed(client, monkeypatch):
    """A designed module with two versions: version 2 rewords slide 1 and adds a slide before the SBI one."""
    config.set_api_key("sk-ant-test-key-1234567890")
    monkeypatch.setattr(ai, "structured", FakeClaude({"s1": ORIG}))
    r = client.post("/api/write/generate", json={"script": script.EXAMPLE, "mode": "design"}).json()
    assert wait(client, r["job"], 240)["status"] == "done"
    pid = r["project"]
    edited = script.EXAMPLE.replace("Feedback is how good teams get better.", "Feedback is how good teams grow.").replace("## The SBI model", "## A new idea\nShow: One · Two\nSay: Something new.\n\n## The SBI model")
    assert edited != script.EXAMPLE
    monkeypatch.setattr(ai, "structured", FakeClaude({"s1": NEW}))
    out = client.post(f"/api/projects/{pid}/apply", json={"script": edited}).json()
    assert wait(client, out["job"], 240)["status"] == "done"
    return pid, edited


def test_versions_know_where_they_came_from_and_can_be_named(client):
    assert [projects.kind_of(n) for n in ("First design", "Quick layout", "Script edited (1 slide redesigned)", "Assistant: 2 visual changes", "Restored version 2", "Imported from a file", "")] == \
        ["design", "quick", "script", "assistant", "restore", "import", "design"]
    pid = _designed_project(client)
    assert client.patch(f"/api/projects/{pid}/versions/1", json={"label": "  Sent  to legal "}).json() == {"n": 1, "label": "Sent to legal"}
    v = client.get(f"/api/projects/{pid}").json()["versions"][0]
    assert v["label"] == "Sent to legal" and v["kind"] == "quick"
    assert client.get(f"/api/projects/{pid}/export").json()["versions"][0]["label"] == "Sent to legal"        # the name travels in the file
    got = client.post("/api/projects/import", files={"file": ("m.json", client.get(f"/api/projects/{pid}/export").content, "application/json")}).json()
    assert client.get(f"/api/projects/{got['project']}").json()["versions"][0]["label"] == "Sent to legal"
    assert client.patch(f"/api/projects/{pid}/versions/1", json={"label": ""}).json()["label"] == ""
    assert client.patch(f"/api/projects/{pid}/versions/1", json={"label": "x" * 61}).status_code == 400
    assert client.patch(f"/api/projects/{pid}/versions/9", json={"label": "x"}).status_code == 400
    assert client.patch("/api/projects/nope/versions/1", json={"label": "x"}).status_code == 404


def test_comparing_shows_the_script_and_each_slide(client, designed):
    pid, edited = designed
    c = client.get(f"/api/projects/{pid}/compare", params={"a": 1}).json()
    assert c["a"] == 1 and c["b"] == 2 and c["reason"] == "" and c["has_draft"] is False
    st = {r["id"]: r["status"] for r in c["slides"]}
    assert st["s1"] == "changed" and st["s2"] == "same" and st["s3"] == "same" and st["s0"] == "same"
    assert [a["title"] for a in c["added"]] == ["A new idea"]                                        # in the current version, not in version 1
    ops = {r["op"] for r in c["script"]}
    assert {"del", "add", "same"} <= ops
    assert any(r["op"] == "del" and "Feedback is how good teams get better." in r["text"] for r in c["script"])
    assert any(r["op"] == "add" and "Feedback is how good teams grow." in r["text"] for r in c["script"])
    assert client.get(f"/api/projects/{pid}/compare", params={"a": 9}).status_code == 404


def test_one_slide_comes_back_with_its_design_and_nothing_else_changes(client, designed, monkeypatch):
    pid, edited = designed
    boom = FakeClaude(); monkeypatch.setattr(ai, "structured", boom)
    before = projects.slides(pid)
    r = client.post(f"/api/projects/{pid}/restore-slide", json={"version": 1, "slide": "s1"})
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["current"] == 3 and v["versions"][-1]["kind"] == "restore" and "from version 1" in v["versions"][-1]["note"]
    assert not boom.requests                                                                         # no Claude call: it is a restore
    assert "Feedback is how good teams get better." in v["script"] and "A new idea" in v["script"]        # slide 1 as it was; the new slide stays
    after = projects.slides(pid)
    assert "ORIGINAL ONE" in after["s1"]["html"] and "REWRITTEN ONE" not in after["s1"]["html"]
    assert after["s2"]["html"] == before["s2"]["html"] and after["s3"]["html"] == before["s3"]["html"]      # the others are as they were
    assert "ORIGINAL ONE" in client.get(f"/api/projects/{pid}/module.html").text
    again = client.post(f"/api/projects/{pid}/restore-slide", json={"version": 1, "slide": "s1"})
    assert again.status_code == 400 and "already the same" in again.json()["detail"]


def test_a_slide_that_was_removed_goes_back_where_it_was(client, designed, monkeypatch):
    pid, edited = designed
    dropped = edited.replace("## A new idea\nShow: One · Two\nSay: Something new.\n\n", "")
    assert dropped != edited
    monkeypatch.setattr(ai, "structured", FakeClaude())
    out = client.put(f"/api/projects/{pid}/script", json={"script": dropped}).json()                    # version 3 drops the slide
    assert wait(client, out["job"], 240)["status"] == "done"
    c = client.get(f"/api/projects/{pid}/compare", params={"a": 2}).json()
    row = next(r for r in c["slides"] if r["title"] == "A new idea")
    assert row["status"] == "removed" and row["restorable"] is True
    r = client.post(f"/api/projects/{pid}/restore-slide", json={"version": 2, "slide": row["id"]})
    assert r.status_code == 200, r.text
    titles = [x["title"] for x in r.json()["outline"]["slides"]]
    assert titles.index("A new idea") == titles.index("The SBI model") - 1                              # back right before the slide it preceded
    assert "Something new." in projects.get(pid)["script"] and r.json()["versions"][-1]["kind"] == "restore"


def test_restoring_a_slide_needs_the_script_settled_and_real_designs(client, designed):
    pid, edited = designed
    client.patch(f"/api/projects/{pid}", json={"script": edited + "\n## Draft\nSay: Not yet.\n"})
    r = client.post(f"/api/projects/{pid}/restore-slide", json={"version": 1, "slide": "s1"})
    assert r.status_code == 409 and "aren't in the slides yet" in r.json()["detail"]
    client.patch(f"/api/projects/{pid}", json={"script": edited})                                     # undone: no draft left
    assert client.post(f"/api/projects/{pid}/restore-slide", json={"version": 1, "slide": "s9"}).status_code == 400
    q = _designed_project(client, script.EXAMPLE.replace("Feedback", "Praise", 1))                    # a quick layout has no separate slide designs
    projects.save_version(q, projects.version_html(q, 1), None, "Script edited", script_text=script.EXAMPLE)
    bad = client.post(f"/api/projects/{q}/restore-slide", json={"version": 1, "slide": "s1"})
    assert bad.status_code == 400 and "Quick layout" in bad.json()["detail"] or "quick layout" in bad.json()["detail"].lower()
