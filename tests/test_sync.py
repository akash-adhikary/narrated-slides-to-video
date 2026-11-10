"""Graphics come with the words that bring them: one graphic shows as its sentence starts; a sentence that names several things
shows each as it is said (a beat early, so it is readable as the word is heard). The video and the page's player agree."""
import pytest
from playwright.sync_api import sync_playwright
from html2mp4 import cli, compose, config, script

S = ("Title: T\n## A\nSay: First we talk about one big idea here today.\nSay: Then easy, medium and hard.\n"
     "Say: Both parts share one cue right here.\n")
INNER = ('<h2 class="t-heading" data-c="0" data-cue="big idea">Big idea</h2>'
         '<div class="t-lead" data-c="1" data-cue="easy">Easy</div><div class="t-lead" data-c="1" data-cue="medium">Medium</div>'
         '<div class="t-lead" data-c="1" data-cue="hard">Hard</div>'
         '<div class="t-lead" data-c="2" data-cue="right here">One</div><div class="t-lead" data-c="2" data-cue="Right here!">Two</div>')


def page(tmp_path):
    m = script.parse(S)
    f = tmp_path / "m.html"; f.write_text(compose.assemble(m, config.brand(), [("custom", INNER)], "", motion="calm"))
    return f


def words(text, per=0.4): return [[w, round(i * per, 2)] for i, w in enumerate(cli._norm_word(x) for x in text.split())]


def test_the_video_shows_one_graphic_with_its_sentence_and_a_list_word_by_word(tmp_path):
    f = page(tmp_path); m = script.parse(S)
    times = [[words(t) for t in m.slides[0].say]]
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(); pg.goto(f.as_uri())
        pg.evaluate(cli.PAGE_JS, ["s1"]); pg.evaluate("t => __html2mp4.setWordTimes(t)", times)
        d = pg.evaluate("[...document.querySelectorAll('#s1 [data-cue]')].map(e => [e.getAttribute('data-cue'), parseFloat(e.style.getPropertyValue('--d') || 0)])")
        b.close()
    d = dict((k, v) for k, v in d[:4]) | {"pair": [v for k, v in d[4:]]}
    assert d["big idea"] == 0                                          # alone in its sentence: with the sentence, not 1.6 s into it
    assert d["easy"] == pytest.approx(0.4 - 0.25) and d["medium"] == pytest.approx(0.8 - 0.25) and d["hard"] == pytest.approx(1.6 - 0.25)   # each a beat before its word
    assert d["pair"] == [0, 0]                                         # two parts of one graphic sharing a cue are one thing


def test_the_player_follows_the_same_rule(tmp_path):
    f = page(tmp_path)
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(); pg.goto(f.as_uri())
        pg.evaluate("""() => { window.__t = {}; window.__on = {}; const T = () => performance.now();
            addEventListener('message', e => { if (e.data && e.data.html2mp4 === 'step' && !(e.data.pos in __t)) __t[e.data.pos] = T(); });
            new MutationObserver(ms => ms.forEach(m => { const e = m.target; const k = e.getAttribute('data-cue');
              if (k && e.classList.contains('on') && !(k in __on)) __on[k] = T(); })).observe(document.getElementById('stage'), {subtree: true, attributes: true, attributeFilter: ['class']}); }""")
        pg.click("#play")
        pg.wait_for_function("window.__on && 'hard' in __on && 'right here' in __on", timeout=40000)
        t, on = pg.evaluate("__t"), pg.evaluate("__on"); b.close()
    since = lambda cue, step: (on[cue] - t[str(step)]) / 1000
    assert ("big idea" not in on or since("big idea", 0) < 0.3) and since("right here", 2) < 0.3      # with the sentence (the first is up before Play)
    assert since("easy", 1) < since("medium", 1) < since("hard", 1) and since("hard", 1) > 0.5  # in turn, as each is said


def test_a_narration_label_and_quotes_are_not_read_aloud():
    m = script.parse('A title\n\nScene 1: Hook (0:00–0:15)\nNarration: "Quick challenge. You have ten seconds. Ready?"\n\nVisual: a countdown\n')
    assert m.slides[0].say == ["Quick challenge.", "You have ten seconds.", "Ready?"] and m.slides[0].screen == "a countdown"
    m = script.parse('A title\nScene 1: One\nVoiceover: “It started with frustration. Everyone waited.”\n')
    assert m.slides[0].say == ["It started with frustration.", "Everyone waited."]
    m = script.parse('A title\nScene 1: One\nShe said "yes" and then "no" to it. Then we left.\n')    # quotes inside a sentence stay
    assert m.slides[0].say == ['She said "yes" and then "no" to it.', "Then we left."]
