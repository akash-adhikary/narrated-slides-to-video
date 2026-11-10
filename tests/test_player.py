"""The review player's studio voice, driven in a real browser with a controllable fake audio element and routed API calls."""
import json, pathlib
import pytest
from playwright.sync_api import sync_playwright
from html2mp4 import compose, config, script

SCRIPT = "Title: T\n## One\nShow: Alpha · Beta\nSay: First the alpha.\nSay: Then the beta.\nSay: And the gamma last.\nSay: Finally the delta."

FAKE_AUDIO = """
window.__a = {created: [], mode: 'ok', failFirst: 0, dur: 500, plays: 0};
window.Audio = class {
  constructor(src){ this.src = src; this.currentTime = 0; this.playbackRate = 1; this._l = {}; this.error = null; window.__a.created.push(src); }
  addEventListener(n, f){ (this._l[n] = this._l[n] || []).push(f); }
  _emit(n){ (this._l[n] || []).forEach(f => f()); }
  pause(){ this._stopped = true; }
  play(){
    const A = window.__a; A.plays++;
    if (A.mode === 'reject') return Promise.reject(Object.assign(new Error('blocked'), {name: 'NotAllowedError'}));
    const fail = A.mode === 'error' || A.failFirst > 0; if (A.failFirst > 0) A.failFirst--;
    if (fail) { setTimeout(() => { this.error = {code: 4}; this.onerror && this.onerror(); }, 10); return Promise.reject(Object.assign(new Error('nope'), {name: 'NotSupportedError'})); }
    if (A.mode === 'silent') return new Promise(() => {});
    setTimeout(() => { if (!this._stopped) this._emit('playing'); }, 10);
    setTimeout(() => { if (!this._stopped) { this.currentTime = 1; this.onended && this.onended(); } }, A.dur);
    return Promise.resolve();
  }
};
window.__s = {spoken: [], dur: 400};
window.SpeechSynthesisUtterance = class { constructor(t){ this.text = t; } };
Object.defineProperty(window, 'speechSynthesis', {configurable: true, value: {
  getVoices: () => [{name: 'Test voice', lang: 'en-US'}], onvoiceschanged: null, cancel(){}, resume(){},
  speak(u){ window.__s.spoken.push(u.text); setTimeout(() => u.onend && u.onend(), window.__s.dur); } }});
"""


@pytest.fixture
def player(tmp_path):
    m = script.parse(SCRIPT)
    chunks = [["a", "b", "c", "d"]]
    words = [[[["first", 0.1]], [["then", 0.1]], [["and", 0.1]], [["finally", 0.1]]]]
    ready = {"status": "done", "progress": 1, "label": "Ready", "error": "", "urls": [[f"/api/projects/p1/narration/audio/0/{i}" for i in range(4)]], "times": words}
    html = (compose.basic_module(m, dict(config.DEFAULT_BRAND)))
    with sync_playwright() as p:
        browser = p.chromium.launch(); page = browser.new_page(viewport={"width": 1100, "height": 700})
        state = {"posts": 0, "ready": ready, "job": None, "down": 0}
        page.add_init_script(FAKE_AUDIO)

        def route(r):
            url, method = r.request.url.split("?")[0], r.request.method
            if url.endswith("/m.html"): return r.fulfill(status=200, content_type="text/html", body=html)
            if method == "POST" and url.endswith("/narration"):
                state["posts"] += 1
                if state["down"] > 0: state["down"] -= 1; return r.abort()                       # the Studio is restarting: connection refused
                body = {"id": None, "ready": state["ready"]} if not state["job"] else {"id": "job1", "ready": None}
                return r.fulfill(status=200, content_type="application/json", body=json.dumps(body))
            if "/api/narration/job1" in url:
                return r.fulfill(status=200, content_type="application/json", body=json.dumps(state["job"]))
            r.fulfill(status=404, content_type="application/json", body="{}")
        page.route("http://studio.test/**", route)
        page.route("https://fonts.*/**", lambda r: r.abort())
        page.goto("http://studio.test/m.html?studio=p1&v=1")
        yield page, state
        browser.close()


def ev(page, js): return page.evaluate(js)
def notice(page): return page.inner_text("#notice") if page.is_visible("#notice") else ""
def pos(page): return page.inner_text("#bar .pos")


def start_studio(page):
    page.click("#studiovoice"); page.wait_for_function("document.getElementById('studiovoice').getAttribute('aria-pressed') === 'true'")


def test_studio_voice_plays_sentence_after_sentence_and_preloads_the_next(player):
    page, _ = player; start_studio(page); page.click("#play")
    page.wait_for_function("window.__a.created.length >= 2")
    created = ev(page, "window.__a.created")
    assert created[0].endswith("/audio/0/0") and created[1].endswith("/audio/0/1")                       # the next one was fetched while the first plays
    page.wait_for_function("document.querySelector('#bar .pos').textContent.startsWith('3')", timeout=5000)
    assert notice(page) == ""


def test_a_lost_studio_voice_reconnects_once_and_carries_on(player):
    page, state = player; start_studio(page)
    ev(page, "window.__a.failFirst = 1"); page.click("#play")
    page.wait_for_function("window.__a.plays >= 2", timeout=5000)                                          # the same sentence is tried again
    assert state["posts"] == 2                                                                              # reconnected through the Studio
    page.wait_for_function("document.querySelector('#bar .pos').textContent.startsWith('2')", timeout=5000)  # and the narration went on, with sound
    assert ev(page, "document.getElementById('studiovoice').getAttribute('aria-pressed')") == "true"


def test_when_it_keeps_failing_it_says_so_and_uses_the_browser_voice(player):
    page, state = player; start_studio(page)
    ev(page, "window.__a.mode = 'error'"); page.click("#play")
    page.wait_for_function("window.__s.spoken.length >= 1", timeout=8000)                                   # the browser voice took over, audibly
    assert "isn't available" in notice(page) and "browser's voice" in notice(page)
    assert ev(page, "document.getElementById('studiovoice').getAttribute('aria-pressed')") == "false"
    assert ev(page, "document.getElementById('play').textContent") == "Pause"                              # still playing, not stuck


def test_a_browser_that_blocks_sound_pauses_with_a_message(player):
    page, _ = player; start_studio(page)
    ev(page, "window.__a.mode = 'reject'"); page.click("#play")
    page.wait_for_function("document.getElementById('play').textContent === 'Play'", timeout=5000)
    assert "blocked the sound" in notice(page)


def test_a_sound_that_never_starts_is_not_waited_for_forever(player):
    page, _ = player; start_studio(page)
    ev(page, "window.__h2mWatchdogMs = 300; window.__a.mode = 'silent'"); page.click("#play")
    page.wait_for_function("window.__a.plays >= 2", timeout=5000)                                           # watchdog fired and it reconnected
    ev(page, "window.__a.mode = 'ok'")


def test_the_studio_voice_takes_over_at_the_next_sentence_not_mid_sentence(player):
    page, state = player
    ev(page, "window.__s.dur = 900")
    state["job"] = {"status": "running", "progress": 0.3, "label": "Making the voice: sentence 2 of 4", "error": "", "done": 1, "total": 4}
    page.click("#play"); page.wait_for_function("window.__s.spoken.length === 1")                          # browser voice speaks sentence one
    page.click("#studiovoice")
    page.wait_for_function("document.getElementById('studiovoice').textContent.startsWith('Preparing 1/4')")
    assert "Making the voice: sentence 2 of 4" in notice(page) and "browser voice is playing" in notice(page)
    state["job"] = {**state["ready"], "id": "x"}                                                            # preparation finishes mid-sentence
    page.wait_for_function("document.getElementById('studiovoice').getAttribute('aria-pressed') === 'true'", timeout=5000)
    assert ev(page, "window.__s.spoken.length") == 1 and ev(page, "window.__a.created.length") == 0         # the sentence is NOT restarted
    page.wait_for_function("window.__a.created.length >= 1", timeout=5000)                                  # the next sentence is in the studio voice
    assert ev(page, "window.__s.spoken.length") == 1


def test_clicking_again_while_preparing_cancels(player):
    page, state = player
    state["job"] = {"status": "running", "progress": 0.1, "label": "Loading the voice…", "error": "", "done": 0, "total": 5}
    page.click("#studiovoice"); page.wait_for_function("document.getElementById('studiovoice').textContent.startsWith('Preparing')")
    page.click("#studiovoice")
    page.wait_for_function("document.getElementById('studiovoice').textContent === 'Studio voice'")
    assert notice(page) == "" and ev(page, "document.getElementById('studiovoice').getAttribute('aria-pressed')") == "false"


def test_a_failed_preparation_is_explained(player):
    page, state = player
    state["job"] = {"status": "failed", "progress": 0, "label": "x", "error": "The studio voice couldn't be prepared (OSError: disk full).", "done": 0, "total": 5}
    page.click("#studiovoice"); page.wait_for_function("document.getElementById('notice').textContent.includes('disk full')")
    assert ev(page, "document.getElementById('studiovoice').textContent") == "Studio voice"


def test_a_studio_that_is_restarting_is_waited_for(player):
    page, state = player; start_studio(page)
    ev(page, "window.__a.failFirst = 1"); state["down"] = 2                  # first sentence fails; the Studio is away for two reconnect attempts
    page.click("#play")
    page.wait_for_function("document.getElementById('notice').textContent.includes('try 2')", timeout=6000)    # it says it is retrying
    page.wait_for_function("document.querySelector('#bar .pos').textContent.startsWith('2')", timeout=10000)   # the Studio came back: narration carried on
    assert ev(page, "document.getElementById('studiovoice').getAttribute('aria-pressed')") == "true"
    assert state["posts"] >= 4 and ev(page, "window.__s.spoken.length") == 0                                  # never fell back to the browser voice


def test_giving_up_takes_a_few_attempts_not_one(player):
    page, state = player; start_studio(page)
    ev(page, "window.__a.failFirst = 1"); state["down"] = 99; page.click("#play")
    page.wait_for_function("document.getElementById('notice').textContent.includes('isn\\'t available')", timeout=15000)
    assert state["posts"] >= 6                                                                                  # 1 to start + 5 reconnect attempts
    assert ev(page, "document.getElementById('studiovoice').getAttribute('aria-pressed')") == "false"
