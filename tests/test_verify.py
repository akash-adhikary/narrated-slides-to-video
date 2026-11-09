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
    ("<script>x()</script>", "", "scripts"), ('<img src="a.png">', "", "isn't allowed"), ('<a href="https://x.y">x</a>', "", "outside links"),
    ('<div onclick="x()">x</div>', "", "event handlers"), ("<p>x</p>", "#s1 p{animation:a 1s}", "animations"),
    ("<p>x</p>", "p{color:red}", "must start with #s1"), ("<p>x</p>", "#s1 p{background:url(a.png)}", "url()"),
])
def test_static_rules(html, css, expect):
    assert any(expect in p for p in verify.static_issues("s1", html, css))


def test_banned_terms():
    assert verify.static_issues("s1", "<p>Career Pathing Programme</p>", "", ["Career Pathing"])
