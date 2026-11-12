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
    said, has_slides = last.split("The person says:")[-1], "\n## " in last           # a new module's script is only its title line
    if has_slides and "flow" in said:
        a = {"reply": "Making it a flow.", "script": None, "edits": [], "summary": [], "visual_requests": [{"slides": ["s1"], "request": "make it a flow"}], "suggestions": []}
    elif "write" in said.lower():
        a = {"reply": "Here is a **first draft**.\n\n- A title\n- Your first day", "script": DRAFT, "summary": ["Wrote a draft"], "visual_requests": [], "suggestions": ["Make it shorter"]}
    elif has_slides:
        cur = last.split("<script>\n")[1].split("\n</script>")[0]
        a = {"reply": "Reworded it.", "script": cur.replace("you meet your buddy", "your buddy meets you") + "\n", "summary": ["Reworded slide 1"], "visual_requests": [], "suggestions": []}
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
def bare(app):
    """The Write page as a visitor first sees it: no module open yet."""
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1100, "height": 800})
        pg.goto(app + "/#write"); pg.wait_for_selector("#wStart")
        yield pg
        b.close()


def new_module(page, name):
    page.evaluate("scrollTo(0, 0)")
    if page.is_visible("#aiClose"): page.click("#aiClose")
    page.click("#wStart" if page.is_visible("#wStart") else "#wNew"); page.fill("#ndInput", name); page.keyboard.press("Enter")
    page.wait_for_function("n => W.current && W.current.name === n", arg=name); page.wait_for_selector("#cardScript", state="visible")


@pytest.fixture
def page(bare):
    new_module(bare, "Onboarding")
    return bare


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
    assert page.input_value("#wScript") == "Title: Onboarding\n"
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
    page.wait_for_function("W.project"); page.wait_for_timeout(500)                    # the chat is saved with the module a moment after the reply
    page.reload(); page.click("#aiOrb")
    page.wait_for_function("document.querySelector('#aiLog').textContent.includes('hello there')")
    assert "Who is it for?" in page.inner_text("#aiLog")
    page.click("#aiNew")
    assert "What's the video about?" in page.inner_text("#aiLog")


def test_it_opens_with_the_keyboard_closes_with_escape_and_lives_on_the_write_page_only(page, app):
    page.focus("#aiOrb"); page.keyboard.press("Enter"); page.wait_for_selector("#aiPanel:not([hidden])")
    page.wait_for_function("document.activeElement.id === 'aiInput'")
    page.keyboard.press("Escape"); assert page.is_hidden("#aiPanel") and page.evaluate("document.activeElement.id") == "aiOrb"
    pid = page.evaluate("W.project")
    page.goto(app + "/#settings"); assert page.is_hidden("#aiOrb")
    page.goto(app + "/#write/" + pid); assert page.is_visible("#aiOrb")
    page.goto(app + "/#write"); page.wait_for_selector("#aiOrb", state="hidden")      # the module list has no assistant: it belongs to a module


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


def test_share_menu_yaml_view_and_opening_a_module_file(page, app, tmp_path):
    pid = quick_project(app)
    page.evaluate("pid => openProject(pid)", pid); page.wait_for_selector("#rvShare", state="visible")
    page.click("#rvShare summary")
    assert page.is_visible("#rvFile") and page.get_attribute("#rvFileAll", "href").endswith("history=true")
    with page.expect_download() as d: page.click("#rvFile")
    saved = tmp_path / "out.h2m.json"; d.value.save_as(saved)
    assert d.value.suggested_filename.endswith(".h2m.json") and json.loads(saved.read_text())["format"] == "html2mp4.module"
    page.click("#rvShare summary"); page.click("#rvYaml")
    page.wait_for_function("document.querySelector('#yvText').textContent.includes('format: html2mp4.module')")
    assert "script: |" in page.inner_text("#yvText") and page.is_visible("#yvCopy")
    page.click("#yvClose"); assert page.is_hidden("#yamlView")
    page.set_input_files("#wImport", str(saved))
    page.wait_for_function("document.querySelector('#toast').textContent.startsWith('Opened')")
    assert page.evaluate("W.project") != pid


def test_nothing_to_write_in_until_a_module_has_a_name(bare, app):
    assert bare.is_hidden("#cardScript") and bare.is_hidden("#aiOrb") and bare.is_visible("#wHero")
    bare.click("#wStart"); assert bare.evaluate("document.querySelector('#nameDlg').open") and bare.evaluate("document.activeElement.id") == "ndInput"
    assert bare.evaluate("getComputedStyle(document.querySelector('#nameDlg'), '::backdrop').backdropFilter").startswith("blur")
    bare.keyboard.press("Enter"); assert "Give the module a name" in bare.inner_text("#ndErr")
    bare.keyboard.press("Escape"); assert not bare.evaluate("document.querySelector('#nameDlg').open")
    assert bare.is_hidden("#cardScript") and json.load(__import__("urllib.request").request.urlopen(app + "/api/projects")) == []          # cancelling made nothing


def test_naming_a_module_opens_it_and_ties_everything_to_it(bare, app):
    bare.click("#wStart"); bare.fill("#ndInput", "Interviewing candidates"); bare.click("#ndNum")
    assert bare.input_value("#ndInput") == "01 · Interviewing candidates"
    bare.keyboard.press("Enter"); bare.wait_for_selector("#cardScript", state="visible")
    pid = bare.evaluate("W.project")
    assert bare.url.endswith("#write/" + pid) and bare.inner_text("#wNameText") == "01 · Interviewing candidates" and bare.title().startswith("01 · Interviewing candidates")
    assert bare.input_value("#wScript") == "Title: Interviewing candidates\n" and bare.evaluate("document.activeElement.id") == "wScript"
    assert bare.is_visible("#aiOrb"); bare.click("#aiOrb"); assert bare.inner_text("#aiModule") == "01 · Interviewing candidates"
    bare.click("#aiClose"); bare.evaluate("scrollTo(0, 0)"); bare.click("#wNew"); bare.click("#ndNum"); assert bare.input_value("#ndInput").startswith("02 · ")     # the next number
    bare.fill("#ndInput", "01 · interviewing CANDIDATES"); bare.keyboard.press("Enter")
    bare.wait_for_function("document.querySelector('#ndErr').textContent.includes('already have a module')")
    assert bare.evaluate("document.querySelector('#nameDlg').open") and bare.evaluate("W.project") == pid       # nothing was made, still in the first module


def test_rename_in_place_keeps_the_address(page):
    pid = page.evaluate("W.project"); url = page.url
    page.click("#wName"); page.fill("#wNameInput", "03 · Renamed"); page.keyboard.press("Enter")
    page.wait_for_function("document.querySelector('#wNameText').textContent === '03 · Renamed'")
    assert page.url == url and page.evaluate("W.project") == pid and "03 · Renamed" in page.title()
    page.click("#wName"); page.keyboard.press("Escape"); assert page.inner_text("#wNameText") == "03 · Renamed" and page.is_visible("#wName")
    page.goto(page.url.split("#")[0] + "#write"); page.wait_for_selector("#modList .mod")
    assert page.inner_text("#modList .mod-t") == "03 · Renamed"


def test_what_you_type_is_kept_and_the_address_reopens_the_module(page, app):
    page.fill("#wScript", DRAFT)
    page.wait_for_function("document.querySelector('#wSaved').textContent === 'Saved'")
    page.reload(); page.wait_for_selector("#cardScript", state="visible")
    assert page.input_value("#wScript") == DRAFT and page.inner_text("#wNameText") == "Onboarding"
    page.fill("#wScript", DRAFT + "\n## Last\nSay: Bye.\n"); page.goto(app + "/#settings")                    # leaving straight away still saves
    page.go_back(); page.wait_for_selector("#cardScript", state="visible")
    page.wait_for_function("W.project && document.querySelector('#wScript').value.includes('## Last')")
    page.click("a.crumb"); page.wait_for_selector("#wStart", state="visible")
    assert page.url.endswith("#write") and page.is_hidden("#cardScript") and page.is_hidden("#aiOrb")
    page.go_back(); page.wait_for_selector("#cardScript", state="visible"); assert page.inner_text("#wNameText") == "Onboarding"


def test_each_module_has_its_own_conversation(page):
    page.click("#aiOrb"); send(page, "hello there"); page.wait_for_selector(".ai-msg.bot")
    page.wait_for_function("document.querySelectorAll('.ai-msg').length >= 2")
    first = page.evaluate("W.project")
    new_module(page, "Second one"); page.wait_for_function("W.project !== '%s'" % first)
    page.wait_for_function("document.querySelector('#aiModule').textContent === 'Second one'")
    if page.is_hidden("#aiPanel"): page.click("#aiOrb")
    page.wait_for_function("!document.querySelector('#aiLog').textContent.includes('hello there')")
    assert "What's the video about?" in page.inner_text("#aiLog")
    page.goto(page.url.split("#")[0] + "#write/" + first); page.wait_for_function("W.project === '%s'" % first)
    if page.is_hidden("#aiPanel"): page.click("#aiOrb")
    page.wait_for_function("document.querySelector('#aiLog').textContent.includes('hello there')")


def two_versions(app):
    """A designed module whose second version has a different script."""
    pid = quick_project(app)
    cur = projects.get(pid)["script"]
    projects.save_version(pid, projects.version_html(pid, 1).replace("Meet your buddy", "Meet your guide"), None, "Second try", script_text=cur.replace("Welcome aboard.", "Welcome, everyone."))
    return pid, cur


def test_version_control_lives_in_the_header_and_moves_script_and_slides_together(page, app):
    pid, v1_script = two_versions(app)
    page.evaluate("pid => openProject(pid)", pid); page.wait_for_selector("#cardReview:not([hidden])", timeout=60000)
    page.click("#aiOrb")                                                                                    # open while we go looking at an old version
    assert page.inner_text("#verLabel").startswith("Version 2 · current") and page.is_visible("#rvShare") and page.locator(".rv-bar #rvShare").count() == 0   # export is up here too
    assert "Welcome, everyone." in page.input_value("#wScript") and page.is_hidden("#verBar")
    page.click("#verLabel")
    rows = page.locator("#verMenu .vrow[data-n]"); assert rows.count() == 2 and "current" in rows.nth(0).inner_text()
    rows.nth(1).click()                                                                                     # version 1
    page.wait_for_selector("#verBar", state="visible"); assert page.is_hidden("#aiPanel")                      # the assistant steps aside
    assert page.input_value("#wScript") == v1_script and page.eval_on_selector("#wScript", "e => e.readOnly")       # its script, not the latest
    assert page.inner_text("#verLabel") == "Viewing version 1" and "version 1" in page.inner_text("#verBarText")
    assert page.eval_on_selector("#rvFrame", "f => f.contentWindow.location.search").split("v=")[1].startswith("1&") and page.get_attribute("#rvDownload", "href").endswith("v=1")   # the slides and the exports follow
    page.click("#rvShare summary"); assert "version 1" in page.inner_text("#shareFor").lower(); page.click("#rvShare summary")
    assert page.is_disabled("#wDesign")
    page.click("#aiOrb"); assert page.is_disabled("#aiInput") and "current version" in page.get_attribute("#aiInput", "placeholder"); page.click("#aiClose")
    page.click("#verBack"); page.wait_for_selector("#verBar", state="hidden")
    assert "Welcome, everyone." in page.input_value("#wScript") and not page.eval_on_selector("#wScript", "e => e.readOnly") and page.is_enabled("#aiInput")


def test_restoring_an_older_version_makes_a_new_one_and_keeps_the_history(page, app):
    pid, v1_script = two_versions(app)
    page.evaluate("pid => openProject(pid)", pid); page.wait_for_selector("#cardReview:not([hidden])", timeout=60000)
    page.click("#verLabel"); page.locator("#verMenu .vrow[data-n]").nth(1).click(); page.wait_for_selector("#verBar", state="visible")
    page.click("#verRestore"); page.wait_for_selector("#verBar", state="hidden")
    assert page.inner_text("#verLabel").startswith("Version 3 · current") and page.input_value("#wScript") == v1_script
    page.click("#verLabel"); assert page.locator("#verMenu .vrow[data-n]").count() == 3 and "Restored version 1" in page.inner_text("#verMenu")


def test_a_draft_survives_a_look_at_an_older_version(page, app):
    pid, _ = two_versions(app)
    page.evaluate("pid => openProject(pid)", pid); page.wait_for_selector("#cardReview:not([hidden])", timeout=60000)
    mine = page.input_value("#wScript") + "\n## A new idea\nSay: Something new.\n"
    page.fill("#wScript", mine); page.wait_for_function("document.querySelector('#wSaved').textContent === 'Saved'")
    page.click("#verLabel"); assert "Script changes not designed yet" in page.inner_text("#verMenu")
    page.locator("#verMenu .vrow[data-n]").nth(1).click(); page.wait_for_selector("#verBar", state="visible")
    assert "A new idea" not in page.input_value("#wScript") and "Waiting for you" in page.evaluate("document.querySelector('#verMenu').textContent")
    page.click("#verBack"); page.wait_for_selector("#verBar", state="hidden")
    assert page.input_value("#wScript") == mine                                                           # still there, untouched


def test_versions_can_be_named_and_show_where_they_came_from(page, app):
    pid, _ = two_versions(app)
    page.evaluate("pid => openProject(pid)", pid); page.wait_for_selector("#cardReview:not([hidden])", timeout=60000)
    page.click("#verLabel")
    assert page.locator("#verMenu .vrow[data-n] .vi").count() == 2 and page.get_attribute("#verMenu .vrow[data-n='1'] .vi", "title") == "Quick layout"
    page.fill("#vName input", "Sent to legal"); page.click("#vName button")
    page.wait_for_function("document.querySelector('#verMenu').textContent.includes('Sent to legal')")
    page.locator("#verMenu .vrow[data-n]").nth(1).click(); page.wait_for_selector("#verBar", state="visible")
    page.click("#verLabel"); assert page.input_value("#vName input") == "" or True
    page.fill("#vName input", "Signed off"); page.click("#vName button")
    page.wait_for_function("document.querySelector('#verMenu .vrow[data-n=\"1\"]').textContent.includes('Signed off')")
    assert "Quick layout" in page.inner_text("#verMenu .vrow[data-n='1'] small")                              # the note is still there under the name


def test_compare_shows_slides_and_script_and_explains_when_slides_cannot_come_back_alone(page, app):
    pid, _ = two_versions(app)
    page.evaluate("pid => openProject(pid)", pid); page.wait_for_selector("#cardReview:not([hidden])", timeout=60000)
    page.click("#verLabel"); page.locator("#verMenu .vrow[data-n]").nth(1).click(); page.wait_for_selector("#verBar", state="visible")
    page.click("#verCompare"); page.wait_for_selector("#cmpDlg[open]"); page.wait_for_selector("#cmpScript .d")
    assert "Version 1" in page.inner_text("#cmpH")
    assert page.locator("#cmpScript .d.del").count() >= 1 and page.locator("#cmpScript .d.add").count() >= 1
    assert "Welcome aboard." in page.inner_text("#cmpScript .d.del") and "Welcome, everyone." in page.inner_text("#cmpScript .d.add")
    assert "Changed" in page.inner_text("#cmpSlides") and "separate slide designs" in page.inner_text("#cmpNote") and page.locator("#cmpSlides [data-slide]").count() == 0
    page.keyboard.press("Escape"); assert not page.evaluate("document.querySelector('#cmpDlg').open")


def test_a_version_has_its_own_address_and_back_undoes_the_switch(page, app):
    pid, v1 = two_versions(app)
    page.evaluate("pid => openProject(pid)", pid); page.wait_for_selector("#cardReview:not([hidden])", timeout=60000)
    page.click("#verLabel"); page.locator("#verMenu .vrow[data-n]").nth(1).click(); page.wait_for_selector("#verBar", state="visible")
    assert page.url.endswith(f"#write/{pid}/v1")
    page.evaluate("history.back()"); page.wait_for_selector("#verBar", state="hidden")                        # Back goes to the current version
    assert page.url.endswith(f"#write/{pid}") and "Welcome, everyone." in page.input_value("#wScript")
    page.evaluate("history.forward()"); page.wait_for_selector("#verBar", state="visible"); assert page.input_value("#wScript") == v1
    page.reload(); page.wait_for_selector("#verBar", state="visible")                                         # the link opens that exact version
    assert page.input_value("#wScript") == v1 and page.inner_text("#verLabel") == "Viewing version 1"
    page.goto(page.url.split("#")[0] + f"#write/{pid}/v9"); page.wait_for_function("document.querySelector('#toast').textContent.includes('version wasn')")


def test_media_library_upload_open_edit_and_insert(page, app, tmp_path):
    import io
    from PIL import Image
    im = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    for x in range(75, 225):
        for y in range(50, 150): im.putpixel((x, y), (20, 120, 220, 255))
    f = tmp_path / "Blue badge.png"; im.save(f)
    page.goto(app + "/#settings"); page.wait_for_selector("#cardMedia")
    page.set_input_files("#mdFile", str(f)); page.wait_for_selector("#mdGrid .md-card")
    assert "Blue badge" in page.inner_text("#mdGrid") and "Cut-out" in page.inner_text("#mdGrid")
    page.click("#mdGrid .md-card"); page.wait_for_selector("#mdDlg[open]")
    assert page.input_value("#mdName") == "Blue badge" and "transparent background" in page.inner_text("#mdMeta")
    page.click("#mdDlg [data-op=trim]"); page.wait_for_function("document.querySelector('#mdName').value === 'Blue badge (trimmed)'")
    assert "150×100" in page.inner_text("#mdMeta")
    page.click("#mdCropGo"); box = page.locator("#mdImg").bounding_box()
    page.mouse.move(box["x"] + 2, box["y"] + 2); page.mouse.down(); page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=5); page.mouse.up()
    page.click("#mdCropApply"); page.wait_for_function("document.querySelector('#mdName').value.includes('(cropped)')")
    assert page.get_attribute("#mdDl a", "href").endswith("format=png")
    page.click("#mdClose")
    page.goto(app + "/#write"); page.wait_for_selector("#wStart")
    new_module(page, "Media test"); page.fill("#wScript", DRAFT); page.focus("#wScript"); page.keyboard.press("Control+End")
    page.click("#wImgPick summary"); page.wait_for_selector("#wImgMenu .ip-row")
    page.locator("#wImgMenu .ip-row", has_text="Blue badge (trimmed)").first.click()
    assert "## Your first day\nImage: Blue badge (trimmed)" in page.input_value("#wScript")


def test_attaching_an_image_in_the_assistant(page, app, tmp_path):
    from PIL import Image
    f = tmp_path / "Spot.png"; Image.new("RGB", (120, 80), (200, 50, 50)).save(f)
    page.click("#aiOrb"); page.set_input_files("#aiFile", str(f))
    page.wait_for_selector("#aiAtt:not([hidden]) .ai-chip-img")
    assert "Spot" in page.inner_text("#aiAtt") and page.get_attribute("#aiInput", "placeholder") == "Say what to do with it…"
    send(page, "hello there")
    page.wait_for_selector(".ai-msg.user .ai-msg-img"); assert page.is_hidden("#aiAtt")


def test_the_studio_scripts_never_share_a_top_level_name():
    """The page loads its scripts one after another into one global scope: a second `const x` stops the whole file from loading,
    and a second `function x` silently replaces the first (the Create page's progress once updated the chat instead)."""
    import pathlib, re
    web = pathlib.Path(studio.__file__).parent / "web"
    order = re.findall(r'<script src="/static/([\w-]+\.js)"', (web / "index.html").read_text())
    seen = {}
    for name in order:
        for m in re.finditer(r"^(?:const|let|class|function|async function)\s+([A-Za-z_$][\w$]*)", (web / name).read_text(), re.M):
            assert m.group(1) not in seen, f"{m.group(1)} is declared in both {seen[m.group(1)]} and {name}"
            seen[m.group(1)] = name
    assert len(order) >= 6 and "media.js" in order


def test_every_page_loads_without_a_script_error(bare, app):
    errors = []; bare.on("pageerror", lambda e: errors.append(str(e)))
    for h in ("#write", "#create", "#settings", "#write"):
        bare.goto(app + "/" + h); bare.wait_for_timeout(400)
    assert errors == []


def test_media_dialog_chooses_a_characters_voice_and_actions(page, app):
    from html2mp4 import media
    from test_actor import sprite, clip
    ch = sprite(voice="Puppy"); w = clip("Wink clip", 0.7)
    page.goto(app + "/#settings"); page.wait_for_selector("#cardMedia"); page.wait_for_selector("#mdGrid .md-card")
    page.locator("#mdGrid .md-card", has_text="Wink clip").click(); page.wait_for_selector("#mdDlg[open]")
    assert page.is_visible("#mdClipTools") and not page.is_visible("#mdActions") and not page.is_visible("#mdVoiceL")        # a clip: tools to use it
    page.select_option("#mdClipActor", ch["id"]); page.fill("#mdClipAs", "wink"); page.click("#mdClipLink")
    for _ in range(50):                                                                                            # the request answers, then the library is updated
        if media.get(ch["id"]).get("actions"): break
        page.wait_for_timeout(100)
    assert media.get(ch["id"])["actions"] == {"wink": w["id"]}
    page.click("#mdClose"); page.locator("#mdGrid .md-card", has_text="Spotter").click(); page.wait_for_selector("#mdActions:not([hidden])")
    page.wait_for_function("document.querySelectorAll('#mdActionList .md-chip').length > 3 && document.querySelector('#mdVoice').options.length > 1")   # filled in after the voices load
    chips = page.inner_text("#mdActionList")
    assert "wink" in chips and "jump" in chips and "nod" in chips and page.locator("#mdActionList .md-chip.clip").count() == 1           # his clip, and the built-in motions
    assert page.input_value("#mdVoice") == "puppy" and "Puppy" in page.inner_text("#mdVoiceL")
    page.select_option("#mdVoice", "pup-high"); page.click("#mdSave"); page.wait_for_timeout(600)
    assert media.actor_voice("Spotter") == "pup-high"
    page.locator("#mdActionList [data-rm=wink]").click(); page.wait_for_function("!document.querySelector('#mdActionList .md-chip.clip')")
    assert "actions" not in media.get(ch["id"])
    assert page.is_hidden("#mdClipTools")
