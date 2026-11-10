"""The chat in a real browser: a scripted stand-in answers, so this checks what the person sees and can do."""
import json, socket, threading, time
import pytest
import uvicorn
from playwright.sync_api import sync_playwright
from html2mp4 import ai, config, projects, studio

DRAFT = "Title: Onboarding Basics\nSubtitle: Week one\nSay: Welcome aboard.\n\n## Your first day\nShow: Meet your buddy · Set up your laptop\nNote: a flow of two steps\nSay: On day one you meet your buddy.\nSay: Then you set up your laptop.\n"


class U: input_tokens, output_tokens = 2000, 400


def fake(system, content, schema, effort="low", max_tokens=0, on_text=None, on_thinking=None, messages=None):
    last = messages[-1]["content"]
    if "boom" in last: raise ai.AIError("Anthropic's rate limit was reached. Wait a minute and try again.")
    if "<script>" in last and "flow" in last.split("The person says:")[-1]:
        a = {"reply": "Making it a flow.", "script": None, "edits": [], "summary": [], "visual_requests": [{"slides": ["s1"], "request": "make it a flow"}], "suggestions": []}
    elif "<script>" in last:
        cur = last.split("<script>\n")[1].split("\n</script>")[0]
        a = {"reply": "Reworded it.", "script": cur.replace("you meet your buddy", "your buddy meets you") + "\n", "summary": ["Reworded slide 1"], "visual_requests": [], "suggestions": []}
    elif "write" in last.lower():
        a = {"reply": "Here is a **first draft**.\n\n- A title\n- Your first day", "script": DRAFT, "summary": ["Wrote a draft"], "visual_requests": [], "suggestions": ["Make it shorter"]}
    else:
        a = {"reply": "Who is it for?", "script": None, "summary": [], "visual_requests": [], "suggestions": ["New hires"]}
    txt = json.dumps(a)
    for k in range(0, len(txt), 60):
        if on_text: on_text(txt[:k]); time.sleep(0.03)
    if on_text: on_text(txt)
    return a, U()


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config"); monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "config" / "settings.json")
    monkeypatch.setattr(projects, "MODULES", tmp_path / "modules")
    monkeypatch.setattr(ai, "structured", fake)
    config.set_api_key("sk-ant-test-key-1234567890")
    with socket.socket() as s: s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(studio.app, host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=server.run, daemon=True); t.start()
    while not server.started: time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True; t.join(5)


@pytest.fixture
def page(app):
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1100, "height": 800})
        pg.goto(app + "/#write"); pg.wait_for_selector("#aiOrb")
        yield pg
        b.close()


def idle(page): page.wait_for_function("!C.busy")


def quick_project(app):
    """A module with a quick-layout design (no model needed), ready to be opened on the Write page."""
    import urllib.request
    req = urllib.request.Request(app + "/api/write/generate", data=json.dumps({"script": DRAFT, "mode": "basic"}).encode(), headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req))
    for _ in range(200):
        if json.load(urllib.request.urlopen(f"{app}/api/write/jobs/{r['job']['id']}"))["status"] == "done": return r["project"]
        time.sleep(0.2)
    raise AssertionError("design did not finish")


def send(page, text):
    idle(page); page.fill("#aiInput", text); page.keyboard.press("Enter")


def test_the_assistant_builds_edits_and_undoes_a_script(page):
    assert page.is_hidden("#aiPanel")
    page.click("#wAsk"); page.wait_for_selector("#aiPanel:not([hidden])")
    assert "What's the video about?" in page.inner_text("#aiLog")
    send(page, "I need a video on onboarding")
    page.wait_for_selector(".ai-msg.bot:has-text('Who is it for?')")
    assert page.input_value("#wScript") == ""
    idle(page); page.click("#aiChips button")                        # "New hires" chip
    page.wait_for_selector(".ai-msg.user:has-text('New hires')")
    send(page, "please write it")
    page.wait_for_selector(".ai-card:has-text('Script updated')")
    assert page.input_value("#wScript").startswith("Title: Onboarding Basics")
    assert "first draft" in page.inner_text("#aiLog") and page.locator(".ai-msg.bot b").count() == 1 and page.locator(".ai-msg.bot li").count() == 2
    assert "1 slides" in page.inner_text("#wStats") or "slide" in page.inner_text("#wStats")
    assert page.inner_text(".ai-card .tag") == "ADDED" or page.inner_text(".ai-card .tag").lower() == "added"
    send(page, "reword the buddy line")
    page.wait_for_selector(".ai-card:has-text('Reworded slide 1'), .ai-card .tag:has-text('changed')")
    assert "your buddy meets you" in page.input_value("#wScript")
    page.locator(".ai-card [data-act=undo]").last.click()
    assert "you meet your buddy" in page.input_value("#wScript") and "Undone" in page.inner_text("#aiLog")


def test_an_edit_made_by_hand_is_what_the_assistant_builds_on(page):
    page.fill("#wScript", DRAFT.replace("Welcome aboard.", "Welcome to the team."))
    page.click("#aiOrb"); send(page, "tweak it")
    page.wait_for_selector(".ai-card:has-text('Script updated')")
    assert "Welcome to the team." in page.input_value("#wScript") and "your buddy meets you" in page.input_value("#wScript")


def test_failures_are_shown_plainly_and_the_chat_keeps_working(page):
    page.click("#aiOrb"); send(page, "boom")
    page.wait_for_selector(".ai-msg.err")
    assert "rate limit" in page.inner_text(".ai-msg.err")
    send(page, "write it"); page.wait_for_selector(".ai-card:has-text('Script updated')")
    assert page.is_enabled("#aiSend")


def test_the_conversation_survives_a_reload_and_new_chat_clears_it(page, app):
    page.click("#aiOrb"); send(page, "hello there"); page.wait_for_selector(".ai-msg.bot")
    page.reload(); page.wait_for_selector("#aiOrb"); page.click("#aiOrb")
    assert "hello there" in page.inner_text("#aiLog") and "Who is it for?" in page.inner_text("#aiLog")
    page.click("#aiNew")
    assert "What's the video about?" in page.inner_text("#aiLog")


def test_it_opens_with_the_keyboard_closes_with_escape_and_lives_on_the_write_page_only(page, app):
    page.focus("#aiOrb"); page.keyboard.press("Enter"); page.wait_for_selector("#aiPanel:not([hidden])")
    page.wait_for_function("document.activeElement.id === 'aiInput'")
    page.keyboard.press("Escape"); assert page.is_hidden("#aiPanel") and page.evaluate("document.activeElement.id") == "aiOrb"
    page.goto(app + "/#settings"); assert page.is_hidden("#aiOrb")
    page.goto(app + "/#write"); assert page.is_visible("#aiOrb")


def test_the_chat_fits_a_phone_screen(page):
    page.set_viewport_size({"width": 375, "height": 760}); page.click("#aiOrb")
    box = page.locator("#aiPanel").bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 376 and page.evaluate("document.documentElement.scrollWidth") <= 376


def test_once_the_slides_exist_the_chat_applies_changes_to_them(page, app):
    pid = quick_project(app)
    page.evaluate("pid => openProject(pid)", pid); page.wait_for_selector("#cardReview:not([hidden])", timeout=60000)
    page.click("#aiOrb"); assert page.is_visible("#aiAutoRow")
    send(page, "reword the buddy line")
    page.wait_for_selector(".ai-card:has-text('Script updated')")
    page.locator(".ai-card [data-act=apply]").last.click()
    page.wait_for_selector(".ai-card:has-text('Slides updated')", timeout=90000)
    assert "Undo" not in page.locator(".ai-card").last.inner_text()
    page.wait_for_function("W.current && W.current.current === 2 && W.current.script.includes('your buddy meets you')")


def test_auto_apply_updates_the_slides_without_a_click(page, app):
    pid = quick_project(app)
    page.evaluate("pid => openProject(pid)", pid); page.wait_for_selector("#cardReview:not([hidden])", timeout=60000)
    page.click("#aiOrb"); page.check("#aiAuto")
    send(page, "reword the buddy line")
    page.wait_for_selector(".ai-card:has-text('Slides updated')", timeout=90000)
    page.reload(); page.wait_for_selector("#aiOrb"); page.click("#aiOrb")
    assert page.is_checked("#aiAuto") is True                                  # the choice is remembered


def test_visual_requests_arrive_as_one_card_and_a_quick_layout_explains_why_it_cannot(page, app):
    pid = quick_project(app)
    page.evaluate("pid => openProject(pid)", pid); page.wait_for_selector("#cardReview:not([hidden])", timeout=60000)
    page.click("#aiOrb"); send(page, "make slide 1 a flow")
    page.wait_for_selector(".ai-card:has-text('Change to how it looks')")
    assert "make it a flow" in page.inner_text(".ai-card") and "Your first day" in page.inner_text(".ai-card .tag.look")
    page.locator(".ai-card [data-act=apply]").click()
    page.wait_for_selector(".ai-card .quiet.bad:has-text('Design with Claude')")
    assert page.locator(".ai-card [data-act=apply]").inner_text() == "Try again"
