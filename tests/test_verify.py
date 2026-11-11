import pytest
from html2mp4 import compose, config, script, verify


def brand(): return dict(config.DEFAULT_BRAND)


def run(html, css=""):
    m = script.parse("Title: T\n## One\nSay: First.\nSay: Second.\nSay: Third.")
    r = verify.inspect(compose.assemble(m, brand(), [("custom", html)], css), m, shots=False)
    return {(i.kind, i.step) for i in r["issues"] if i.kind != "invented"}


def test_clean_example_has_no_problems():
    m = script.parse(script.EXAMPLE)
    r = verify.inspect(compose.basic_module(m, brand()), m, shots=False)
    assert [i for i in r["issues"] if i.severity == "error"] == []


def test_font_outside_scale():
    assert ("font", 1) in run('<h2 data-c="0" style="font-size:34px">Heading</h2>')


def test_text_spilling_out_of_its_box():
    css = "#s1 .box{background:var(--surface);border:1px solid var(--line);padding:8px;width:160px;height:50px}"
    assert ("overflow", 2) in run('<h2 data-c="0" class="t-heading">Hi</h2><div class="box" data-c="1"><span class="t-body">Find the right person for the role</span></div>', css)


def test_overlapping_boxes_only_once_both_are_shown():
    css = "#s1 .box{position:absolute;background:var(--surface);border:1px solid var(--line);padding:8px;width:200px;height:80px} #s1 .a{left:0;top:200px} #s1 .b{left:100px;top:220px}"
    found = run('<h2 data-c="0" class="t-heading">Hi</h2><div class="box a t-body" data-c="1">One</div><div class="box b t-body" data-c="2">Two</div>', css)
    assert ("overlap", 3) in found and ("overlap", 2) not in found          # the second box appears at step 3


def test_overlap_can_be_intentional():
    css = "#s1 .box{position:absolute;background:var(--surface);border:1px solid var(--line);width:200px;height:80px} #s1 .a{left:0;top:200px} #s1 .b{left:100px;top:220px}"
    found = run('<h2 data-c="0" class="t-heading">Hi</h2><div class="box a" data-c="1" data-overlay>One</div><div class="box b" data-c="1" data-overlay>Two</div>', css)
    assert not any(k == "overlap" for k, _ in found)


def test_low_contrast_and_footer_zone():
    found = run('<h2 data-c="0" class="t-heading">Hi</h2><p class="t-body" data-c="1" style="color:#10132a">Faint</p>'
                '<p class="t-body" data-c="2" style="position:absolute;left:0;top:590px">Too low</p>')
    assert ("contrast", 2) in found and ("bounds", 3) in found


def test_gradient_headline_is_not_flagged():
    css = "#s1 .g{background:linear-gradient(90deg,#fff,#04d1ff);-webkit-background-clip:text;background-clip:text;color:transparent}"
    assert not any(k == "contrast" for k, _ in run('<h2 class="g t-heading" data-c="0">Gradient</h2>', css))


def test_invented_words_are_a_warning_not_an_error():
    m = script.parse("Title: T\n## One\nSay: Hello world today.")
    r = verify.inspect(compose.assemble(m, brand(), [("custom", '<h2 class="t-heading" data-c="0">Zebra crossing</h2>')]), m, shots=False)
    assert [(i.kind, i.severity) for i in r["issues"] if i.kind == "invented"] == [("invented", "warn")]


@pytest.mark.parametrize("html, css, expect", [
    ("<script>x()</script>", "", "scripts"), ('<img src="a.png">', "", "must come from the media library"), ('<a href="https://x.y">x</a>', "", "outside links"),
    ('<div onclick="x()">x</div>', "", "event handlers"), ("<p>x</p>", "#s1 p{animation:a 1s}", "animations"),
    ("<p>x</p>", "p{color:red}", "must start with #s1"), ("<p>x</p>", "#s1 p{background:url(a.png)}", "url()"),
])
def test_static_rules(html, css, expect):
    assert any(expect in p for p in verify.static_issues("s1", html, css))


def test_banned_terms():
    assert verify.static_issues("s1", "<p>Career Pathing Programme</p>", "", ["Career Pathing"])


def test_gradient_text_is_a_fill_not_a_box():
    """Brand headings use a gradient clipped to the text. Its line height can make the text rect a few px taller than the element:
    that is not text spilling out of a box."""
    css = ("#s1 .g{background:linear-gradient(90deg,#fff,#04d1ff);-webkit-background-clip:text;background-clip:text;color:transparent;"
           "line-height:1.1;letter-spacing:-0.02em;max-width:300px}")
    found = run('<h2 class="g t-heading" data-c="0">How to Interview Candidates <br>at ThoughtSpot</h2>', css)
    assert not any(k in ("overflow", "overlap") for k, _ in found)


def test_motion_rules():
    assert any("your own animations" in x for x in verify.static_issues("s1", "<p>x</p>", "#s1 p{animation:spin 2s infinite}"))
    assert any("your own animations" in x for x in verify.static_issues("s1", "<p>x</p>", "@keyframes a{to{opacity:1}}"))
    assert any("same element as data-c" in x for x in verify.static_issues("s1", '<div class="card amb-float" data-c="1">x</div>', ""))
    assert any("pathLength" in x for x in verify.static_issues("s1", '<svg><path class="draw" d="M0 0L9 9"/></svg>', ""))
    assert verify.static_issues("s1", '<svg><path class="draw" pathLength="1" d="M0 0L9 9"/></svg><div class="amb-float"><span data-c="1" data-fx="pop">x</span></div>', "#s1 .a{transition:opacity 1s}") == []


def test_ambient_loops_do_not_upset_the_measurement():
    html = ('<h2 class="t-heading" data-c="0" data-fx="left">Heading</h2><div class="row"><div class="card t-lead" data-c="1" data-fx="pop">'
            '<svg class="amb-float" width="40" height="40" viewBox="0 0 40 40" aria-label="x"><circle class="draw" pathLength="1" cx="20" cy="20" r="16" fill="none" stroke="var(--accent)" stroke-width="3"/></svg>Alpha</div>'
            '<div class="card t-lead amb-glow-x" data-c="2" data-fx="wipe">Beta</div></div>')
    assert not any(k in ("overflow", "overlap", "bounds") for k, _ in run(html))


def test_the_renderer_anchors_looping_animations_to_absolute_time():
    from playwright.sync_api import sync_playwright
    from html2mp4 import cli
    m = script.parse("Title: T\n## One\nSay: First.\nSay: Second.")
    page_html = compose.assemble(m, brand(), [("custom", '<h2 class="t-heading" data-c="0">One</h2><div class="amb-float" data-overlay style="width:40px;height:40px;background:var(--accent)"></div>')])
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        f = pathlib.Path(tmp) / "m.html"; f.write_text(page_html)
        browser, page = cli.open_page(p, f, 1280)
        page.evaluate(cli.PAGE_JS, ["s1"]); page.evaluate("__html2mp4.reset()")            # reset must cope with endless animations
        times = []
        for et in (0.6, 2.0):                                                               # two different 'first seen' moments
            page.evaluate(f"__html2mp4.show(0,0,{et})"); page.evaluate("__html2mp4.frame(3.0)")
            times.append(page.evaluate("document.getAnimations().filter(a => a.effect.getComputedTiming().iterations === Infinity).map(a => a.currentTime)"))
            page.evaluate("__html2mp4.reset()")
        browser.close()
    assert times[0] and times[0] == times[1] and all(abs(t - 3000) < 1 for t in times[0])    # the loop sits at t = 3 s however the worker got there
