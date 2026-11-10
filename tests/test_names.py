import json
from test_studio import client, _designed_project   # noqa: F401
from html2mp4 import chat, projects, script


def make(client, name):
    r = client.post("/api/projects", json={"name": name}); assert r.status_code == 200, r.text
    return r.json()


def test_a_module_starts_from_its_name(client):
    p = make(client, "08 · Interviewing candidates")
    assert p["name"] == "08 · Interviewing candidates" and p["title"] == "Interviewing candidates"
    assert p["script"] == "Title: Interviewing candidates\n" and p["versions"] == [] and p["id"].startswith("08-Interviewing")
    assert [m["name"] for m in client.get("/api/projects").json()] == ["08 · Interviewing candidates"]


def test_names_are_required_and_unique_ignoring_case(client):
    assert client.post("/api/projects", json={"name": "   "}).status_code == 400
    assert client.post("/api/projects", json={"name": "x" * 81}).status_code == 400
    make(client, "Onboarding")
    dup = client.post("/api/projects", json={"name": "onboarding"})
    assert dup.status_code == 409 and "already have a module called" in dup.json()["detail"]


def test_renaming_keeps_the_address_and_checks_for_clashes(client):
    a, b = make(client, "First"), make(client, "Second")
    r = client.patch(f"/api/projects/{a['id']}", json={"name": "  Renamed   module "}).json()
    assert r["name"] == "Renamed module" and client.get(f"/api/projects/{a['id']}").json()["name"] == "Renamed module"
    clash = client.patch(f"/api/projects/{b['id']}", json={"name": "renamed MODULE"})
    assert clash.status_code == 409
    assert client.patch(f"/api/projects/{b['id']}", json={"name": "Second"}).status_code == 200        # its own name is not a clash
    assert client.patch("/api/projects/nope", json={"name": "x"}).status_code == 404


def test_autosave_keeps_the_script_without_touching_the_designed_one(client):
    p = make(client, "Draft")
    client.patch(f"/api/projects/{p['id']}", json={"script": script.EXAMPLE})
    v = client.get(f"/api/projects/{p['id']}").json()
    assert v["script"] == script.EXAMPLE and v["designed_script"] == ""
    r = client.post(f"/api/projects/{p['id']}/design", json={"script": script.EXAMPLE, "mode": "basic"}).json()
    from test_studio import wait; wait(client, r["job"])
    edited = script.EXAMPLE.replace("Welcome", "Hello", 1)
    client.patch(f"/api/projects/{p['id']}", json={"script": edited})
    v = client.get(f"/api/projects/{p['id']}").json()
    assert v["script"] == edited and v["designed_script"] == script.EXAMPLE and len(v["versions"]) == 1       # the slides still know what they were made from
    assert projects.get(p["id"])["script"] == script.EXAMPLE
    client.patch(f"/api/projects/{p['id']}", json={"script": script.EXAMPLE})
    assert projects.get(p["id"])["draft"] is None                                                              # back to the designed text: no draft


def test_updating_slides_after_an_autosave_still_sees_the_change(client):
    pid = _designed_project(client)
    edited = script.EXAMPLE.replace("Welcome", "Hello", 1)
    client.patch(f"/api/projects/{pid}", json={"script": edited})
    out = client.put(f"/api/projects/{pid}/script", json={"script": edited}).json()
    assert out["job"] is not None                                                                              # not mistaken for "nothing changed"
    from test_studio import wait; wait(client, out["job"])
    assert projects.get(pid)["draft"] is None and projects.get(pid)["script"] == edited


def test_designing_a_new_module_in_place(client):
    p = make(client, "Quick")
    body = {"script": script.EXAMPLE, "mode": "basic"}
    r = client.post(f"/api/projects/{p['id']}/design", json=body).json()
    from test_studio import wait; wait(client, r["job"])
    v = client.get(f"/api/projects/{p['id']}").json()
    assert v["name"] == "Quick" and v["title"] == "Giving Feedback That Lands" and v["versions"][0]["note"] == "Quick layout"   # the video title comes from the script
    assert len(client.get("/api/projects").json()) == 1                                                       # no second module was made
    assert client.post(f"/api/projects/{p['id']}/design", json={"script": script.EXAMPLE, "mode": "design"}).status_code == 400   # no key set


def test_old_modules_are_named_after_their_title(client):
    p = projects.create("Old one", "Title: Old one\n")
    f = projects.folder(p["id"]) / "project.json"
    data = json.loads(f.read_text()); data.pop("name"); f.write_text(json.dumps(data))
    assert client.get("/api/projects").json()[0]["name"] == "Old one"


def test_the_conversation_is_kept_with_the_module(client):
    a, b = make(client, "A"), make(client, "B")
    items = [{"role": "user", "text": "hi"}, {"role": "assistant", "text": "hello"}]
    assert client.put(f"/api/projects/{a['id']}/chat", json={"items": items}).json() == {"ok": True}
    assert client.get(f"/api/projects/{a['id']}/chat").json()["items"] == items and client.get(f"/api/projects/{b['id']}/chat").json()["items"] == []
    client.put(f"/api/projects/{a['id']}/chat", json={"items": [{"text": str(i)} for i in range(90)]})
    assert len(client.get(f"/api/projects/{a['id']}/chat").json()["items"]) == 60
    assert client.get("/api/projects/nope/chat").status_code == 404


def test_the_assistant_is_told_which_module_it_is_working_on():
    seen = {}
    def call(system, content, schema, **kw):
        seen["system"], seen["msg"] = system, kw["messages"][-1]["content"]
        class U: input_tokens, output_tokens = 1, 1
        return {"reply": "ok", "script": None, "summary": [], "visual_requests": [], "suggestions": []}, U()
    chat.turn([{"role": "user", "content": "shorter"}], "Title: T\n\n## A\nSay: Hi.\n", False, {}, call=call, module={"name": "08 · Interviewing candidates", "version": 3})
    assert 'named "08 · Interviewing candidates"' in seen["msg"] and "version 3" in seen["msg"]
    assert "own label for this piece of work" in seen["system"]
    chat.turn([{"role": "user", "content": "x"}], "", False, {}, call=call)
    assert "named" not in seen["msg"]
