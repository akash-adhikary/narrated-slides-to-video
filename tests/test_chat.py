import json, time
import pytest
from fastapi.testclient import TestClient
from html2mp4 import ai, chat, config, projects, script, studio

DRAFT = "Title: Onboarding Basics\nSubtitle: Week one\nSay: Welcome aboard.\n\n## Your first day\nShow: Meet your buddy · Set up your laptop\nNote: a flow of two steps\nSay: On day one you meet your buddy.\nSay: Then you set up your laptop.\n"


class U: input_tokens, output_tokens = 2000, 400


class Fake:
    """Stands in for ai.structured: answers from a queue and records what it was sent."""
    def __init__(self, *answers): self.answers, self.calls = list(answers), []

    def __call__(self, system, content, schema, effort="low", max_tokens=0, on_text=None, on_thinking=None, messages=None):
        self.calls.append({"system": system, "messages": messages, "effort": effort})
        a = self.answers.pop(0)
        full = {"reply": "", "script": None, "summary": [], "visual_requests": [], "suggestions": []} | a
        if on_text: on_text(json.dumps(full))
        return full, U()


def test_partial_reply_reads_a_streaming_answer():
    assert chat.partial_reply('{"reply":"Hel') == "Hel"
    assert chat.partial_reply('{"reply":"Line one\\nLine \\"two\\" \\u00e9') == 'Line one\nLine "two" é'
    assert chat.partial_reply('{"reply":"cut \\u00') == "cut "
    assert chat.partial_reply('{"rep') == ""
    assert chat.partial_reply('{"reply":"done","script":null}') == "done"


def test_a_brief_gets_questions_and_no_script():
    f = Fake({"reply": "Who is it for, and how long?"})
    r = chat.turn([{"role": "user", "content": "I need a video on onboarding"}], call=f)
    assert r["script"] is None and r["changes"] == [] and "how long" in r["reply"]
    sent = f.calls[0]["messages"]
    assert "There is no script yet." in sent[-1]["content"] and "onboarding" in sent[-1]["content"] and f.calls[0]["effort"] == "low"


def test_a_draft_is_parsed_and_summarised():
    f = Fake({"reply": "Here is a first draft.", "script": DRAFT, "summary": ["Wrote a first draft"], "suggestions": ["Make it shorter"]})
    seen = []
    r = chat.turn([{"role": "user", "content": "just write it"}], on_reply=seen.append, call=f)
    assert script.parse(r["script"]).title == "Onboarding Basics" and r["summary"] == ["Wrote a first draft"] and r["suggestions"] == ["Make it shorter"]
    assert [c["kind"] for c in r["changes"]] == ["added", "added"] and r["cost"] > 0 and seen[-1] == "Here is a first draft."


def test_an_edit_sees_the_current_script_and_lists_only_what_changed():
    new = DRAFT.replace("Then you set up your laptop.", "Next you set up your laptop.")
    f = Fake({"reply": "Done.", "script": new, "summary": ["Reworded slide 1"]})
    hist = [{"role": "user", "content": "write it"}, {"role": "assistant", "content": "Here you go."}, {"role": "user", "content": "reword the laptop line"}]
    r = chat.turn(hist, current_script=DRAFT, call=f)
    last = f.calls[0]["messages"][-1]["content"]
    assert "<script>" in last and "Then you set up your laptop." in last and last.endswith("reword the laptop line")
    assert r["changes"] == [{"slide": "s1", "title": "Your first day", "kind": "changed"}]


def test_a_script_that_cannot_be_read_is_retried_once_then_dropped():
    f = Fake({"reply": "Draft", "script": "this is not a script"}, {"reply": "Fixed", "script": DRAFT})
    r = chat.turn([{"role": "user", "content": "write"}], call=f)
    assert r["script"] and len(f.calls) == 2 and "could not be read" in f.calls[1]["messages"][-1]["content"]
    g = Fake({"script": "nope"}, {"script": "still nope"})
    r = chat.turn([{"role": "user", "content": "write"}], call=g)
    assert r["script"] is None and "right format" in r["reply"] and r["summary"] == []


def test_an_unchanged_script_is_not_reported_as_a_change():
    r = chat.turn([{"role": "user", "content": "ok"}], current_script=DRAFT, call=Fake({"reply": "Fine.", "script": DRAFT}))
    assert r["script"] is None and r["changes"] == []


def test_visual_requests_only_when_designed_and_only_for_real_slides():
    ask = {"reply": "Sure.", "visual_requests": [{"slides": ["s1", "s9"], "request": "make it a flow"}]}
    r = chat.turn([{"role": "user", "content": "flow please"}], current_script=DRAFT, designed=True, slides={"s1": {"layout": "cards"}}, call=Fake(ask))
    assert r["visual_requests"] == [{"slides": ["s1"], "request": "make it a flow"}]
    r = chat.turn([{"role": "user", "content": "flow please"}], current_script=DRAFT, designed=False, call=Fake(ask))
    assert r["visual_requests"] == []


def test_a_conversation_must_end_with_the_person():
    with pytest.raises(ai.AIError): chat.turn([{"role": "assistant", "content": "hi"}], call=Fake())


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "config" / "settings.json")
    monkeypatch.setattr(projects, "MODULES", tmp_path / "modules")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    studio.chat_jobs.clear()
    return TestClient(studio.app)


def poll(client, jid):
    for _ in range(100):
        j = client.get(f"/api/write/chat/{jid}").json()
        if j["status"] != "running": return j
        time.sleep(0.05)
    raise AssertionError("chat did not finish")


def test_chat_endpoint_needs_a_key_then_streams_a_turn(client, monkeypatch):
    body = {"messages": [{"role": "user", "content": "write a short onboarding video"}], "script": ""}
    r = client.post("/api/write/chat", json=body)
    assert r.status_code == 400 and "API key" in r.json()["detail"]
    config.set_api_key("sk-ant-test-key-1234567890")
    fake = Fake({"reply": "Here is a draft.", "script": DRAFT, "summary": ["Wrote it"]})
    monkeypatch.setattr(ai, "structured", fake)
    jid = client.post("/api/write/chat", json=body).json()["id"]
    j = poll(client, jid)
    assert j["status"] == "done" and j["result"]["script"].startswith("Title: Onboarding Basics") and j["reply"] == "Here is a draft."
    assert client.post("/api/write/chat", json={"messages": [{"role": "assistant", "content": "x"}]}).status_code == 400
    assert client.get("/api/write/chat/nope").status_code == 404


def test_chat_endpoint_reports_a_failure_plainly(client, monkeypatch):
    config.set_api_key("sk-ant-test-key-1234567890")
    def boom(*a, **k): raise ai.AIError("Anthropic's rate limit was reached. Wait a minute and try again.")
    monkeypatch.setattr(ai, "structured", boom)
    j = poll(client, client.post("/api/write/chat", json={"messages": [{"role": "user", "content": "hi"}]}).json()["id"])
    assert j["status"] == "failed" and "rate limit" in j["error"]


def test_chat_knows_when_the_module_is_designed(client, monkeypatch):
    config.set_api_key("sk-ant-test-key-1234567890")
    p = projects.create("Onboarding Basics", DRAFT)
    fake = Fake({"reply": "ok"}); monkeypatch.setattr(ai, "structured", fake)
    poll(client, client.post("/api/write/chat", json={"messages": [{"role": "user", "content": "hi"}], "script": DRAFT, "project_id": p["id"]}).json()["id"])
    assert "NOT designed" in fake.calls[0]["messages"][-1]["content"]


def test_inserting_a_slide_does_not_mark_the_ones_after_it_as_changed():
    new = DRAFT + "\n## A bonus slide\nSay: One more thing.\n"
    mid = DRAFT.replace("## Your first day", "## A new opener\nSay: Hello again.\n\n## Your first day")
    assert chat.diff(DRAFT, new) == [{"slide": "s2", "title": "A bonus slide", "kind": "added"}]
    assert chat.diff(DRAFT, mid) == [{"slide": "s1", "title": "A new opener", "kind": "added"}]
    assert chat.diff(mid, DRAFT) == [{"slide": "s1", "title": "A new opener", "kind": "removed"}]
    assert chat.diff(DRAFT, DRAFT.replace("Then you set up", "Next you set up")) == [{"slide": "s1", "title": "Your first day", "kind": "changed"}]


def test_the_assistant_is_told_how_slides_are_numbered():
    f = Fake({"reply": "ok"})
    chat.turn([{"role": "user", "content": "change slide 2"}], current_script=DRAFT, call=f)
    ctx = f.calls[0]["messages"][-1]["content"]
    assert "s0 = slide 1: title slide" in ctx and "s1 = slide 2: Your first day" in ctx
