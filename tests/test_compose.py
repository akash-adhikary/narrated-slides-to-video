from html2mp4 import compose, config
from html2mp4.cli import load_scenes
from html2mp4.script import EXAMPLE, parse


def brand():
    return dict(config.DEFAULT_BRAND)


def test_basic_module_round_trips_narration():
    m = parse(EXAMPLE)
    page = compose.basic_module(m, brand())
    scenes = load_scenes(page)
    assert [s["id"] for s in scenes] == ["s0", "s1", "s2", "s3"]
    assert [s["chunks"] for s in scenes] == [m.intro] + [s.say for s in m.slides]
    assert compose.check(page, m) == []


def test_awkward_text_survives():
    tricky = 'Quotes "x", apostrophes it\'s, unicode café — and </script> too.'
    m = parse(f"Title: A <b>bold</b> title\n## Slide & more\nShow: <i>x</i>\nSay: {tricky}")
    page = compose.basic_module(m, brand())
    assert load_scenes(page)[0]["chunks"] == [tricky]
    assert "<b>bold</b>" not in page and "&lt;b&gt;bold&lt;/b&gt;" in page
    assert page.count("</script>") == 2          # only the page's own two script blocks close
    assert compose.check(page, m) == []


def test_no_intro_means_no_title_slide():
    m = parse("Title: T\n## One\nSay: a.\n## Two\nSay: b.")
    page = compose.basic_module(m, brand())
    assert [s["id"] for s in load_scenes(page)] == ["s1", "s2"]


def test_points_spread_across_narration():
    m = parse("Title: T\n## S\nShow: a · b · c · d\nSay: one.\nSay: two.")
    _, inner = compose.basic_slide(m.slides[0])
    cues = [int(x) for x in __import__("re").findall(r'class="card" data-c="(\d)"', inner)]
    assert cues == [0, 0, 1, 1]


def test_check_catches_mismatch():
    m = parse(EXAMPLE)
    page = compose.basic_module(m, brand()).replace("Feedback is how good teams get better.", "Changed.")
    assert any("doesn't match" in p for p in compose.check(page, m))
