import json
import pytest
from html2mp4 import modulefile, projects, script
from test_studio import client, _designed_project   # noqa: F401  (the fixture and helper)


def export(client, pid, **q):
    r = client.get(f"/api/projects/{pid}/export", params=q); assert r.status_code == 200, r.text
    return r


def reopen(client, text, name="m.h2m.json"):
    return client.post("/api/projects/import", files={"file": (name, text.encode(), "application/json")})


def test_export_is_one_readable_file(client):
    pid = _designed_project(client)
    r = export(client, pid)
    assert "attachment" in r.headers["content-disposition"] and ".h2m.json" in r.headers["content-disposition"]
    doc = r.json()
    assert doc["format"] == "html2mp4.module" and doc["schema"] == 2 and doc["title"] == "Giving Feedback That Lands" and doc["name"] == "Giving Feedback That Lands"
    assert doc["script"] == script.EXAMPLE and len(doc["versions"]) == 1 and doc["current"] == 1
    assert "<section" in doc["versions"][0]["html"] and doc["integrity"]["sha256"] == modulefile.checksum(doc)
    assert set(doc["brand"]) <= set(modulefile.BRAND_KEYS)


def test_the_yaml_view_is_the_same_data_and_readable(client):
    pid = _designed_project(client)
    text = export(client, pid, format="yaml", inline="true").text
    assert "content-disposition" not in export(client, pid, format="yaml", inline="true").headers
    assert "script: |" in text and "Title: Giving Feedback That Lands" in text           # block text, not one escaped line
    assert modulefile.loads(text)["doc"]["script"] == script.EXAMPLE
    assert ".h2m.yaml" in export(client, pid, format="yaml").headers["content-disposition"]


@pytest.mark.parametrize("fmt", ["json", "yaml"])
def test_a_file_comes_back_as_an_identical_project(client, fmt):
    pid = _designed_project(client)
    text = export(client, pid, format=fmt).text
    got = reopen(client, text).json()
    assert got["edited"] is False and got["project"] != pid and got["versions"] == 1 and got["designed"] is True
    view = client.get(f"/api/projects/{got['project']}").json()
    assert view["script"] == script.EXAMPLE and view["current"] == 1
    assert client.get(f"/api/projects/{got['project']}/module.html").text == client.get(f"/api/projects/{pid}/module.html").text


def test_history_travels_with_the_file_and_the_current_version_is_kept(client):
    pid = _designed_project(client)
    old = projects.get(pid)["script"]
    projects.save_version(pid, "<html>two</html>", None, "Second try", script_text=old.replace("Welcome", "Hello", 1))
    projects.restore(pid, 1)                                                                # version 3 = version 1 again
    one = export(client, pid).json(); full = export(client, pid, history="true").json()
    assert len(one["versions"]) == 1 and [v["n"] for v in full["versions"]] == [1, 2, 3] and full["current"] == 3
    got = reopen(client, json.dumps(full)).json()
    assert got["versions"] == 3
    view = client.get(f"/api/projects/{got['project']}").json()
    assert [v["note"] for v in view["versions"]][1:] == ["Second try", "Restored version 1"] and view["current"] == 3
    assert view["script"] == old and projects.version_html(got["project"], 2) == "<html>two</html>"


def test_an_undesigned_script_travels_too(client):
    p = projects.create("Just words", script.EXAMPLE)
    doc = export(client, p["id"]).json()
    assert doc["versions"] == [] and doc["current"] == 0
    got = reopen(client, json.dumps(doc)).json()
    assert got["designed"] is False and projects.get(got["project"])["versions"] == []


def test_a_hand_edit_is_noticed_but_not_refused(client):
    pid = _designed_project(client)
    text = export(client, pid, format="yaml").text.replace("Welcome", "Hello there", 1)
    got = reopen(client, text, "m.h2m.yaml").json()
    assert got["edited"] is True
    assert "Hello there" in client.get(f"/api/projects/{got['project']}").json()["script"]


def test_bad_files_say_what_is_wrong(client):
    pid = _designed_project(client)
    doc = export(client, pid).json()
    def err(d): r = reopen(client, d if isinstance(d, str) else json.dumps(d)); assert r.status_code == 422; return r.json()["detail"]
    assert "newer Studio" in err({**doc, "schema": 99})
    assert "no script" in err({**doc, "script": ""})
    assert "points at a version" in err({**doc, "current": 7})
    assert "malformed" in err({**doc, "versions": ["x"]})
    assert "couldn't be read" in err('{"format": "html2mp4.module", "schema": 1, "x": [unclosed')
    assert "script inside" in err({**doc, "script": "not a script"})
    assert client.get("/api/projects/nope/export").status_code == 404
    assert client.get(f"/api/projects/{pid}/export", params={"format": "xml"}).status_code == 400


def test_a_version_1_file_still_opens_and_its_title_becomes_the_name(client):
    pid = _designed_project(client)
    doc = export(client, pid).json()
    old = {k: v for k, v in doc.items() if k != "name"} | {"schema": 1}
    old["integrity"] = {"sha256": modulefile.checksum(old)}
    got = reopen(client, json.dumps(old)).json()
    assert got["edited"] is False and got["name"] == "Giving Feedback That Lands (2)"       # the name is taken by the original, so it gets a number


def test_the_name_travels_in_the_file_and_names_the_download(client):
    r = client.post("/api/projects", json={"name": "07 · Interviewing candidates"}); assert r.status_code == 200
    pid = r.json()["id"]
    out = export(client, pid)
    assert "filename*=UTF-8''07%20%C2%B7%20Interviewing%20candidates.h2m.json" in out.headers["content-disposition"]
    assert out.json()["name"] == "07 · Interviewing candidates" and out.json()["title"] == "Interviewing candidates"
    got = reopen(client, out.text).json()
    assert got["name"] == "07 · Interviewing candidates (2)"
