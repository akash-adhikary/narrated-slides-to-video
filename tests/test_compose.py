import pytest
import pathlib
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
    assert page.count("</script>") == 3          # only the page's own three script blocks close (source, project, player)
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


def test_motion_kit_and_player_are_in_every_module():
    m = parse("Title: T\n## One\nShow: A\nSay: First.")
    page = compose.basic_module(m, brand())
    for piece in ("[data-c][data-fx=pop]", ".draw{", "@property --n", ".flow >", "@keyframes h2m-float", "data-motion=calm"):
        assert piece in page
    assert 'data-motion="lively"' in page and 'data-motion="calm"' in compose.basic_module(m, brand(), motion="calm")
    for ident in ('id="fs"', 'id="speed"', 'id="voice"', 'id="studiovoice"', 'id="cc"', 'id="seek"', "speechSynthesis", "requestFullscreen"):
        assert ident in page


def test_a_module_carries_its_project_and_knows_when_it_was_edited():
    m = parse("Title: T\n## One\nShow: A\nSay: First.")
    page = compose.basic_module(m, brand(), script_text="Title: T\n## One\nShow: A\nSay: First.")
    data = compose.read_project(page)
    assert data["script"].startswith("Title: T") and data["slides"] is None and data["edited"] is False
    assert compose.read_project(page.replace("First.", "Fist.", 1))["edited"] is True          # changed after the Studio wrote it
    assert compose.read_project(compose.basic_module(m, brand())) is None                         # no project block


def test_downloading_embeds_fonts_without_looking_edited(monkeypatch):
    m = parse("Title: T\n## One\nShow: A\nSay: First.")
    b = brand(); b["heading_font"] = b["body_font"] = "Inter"
    monkeypatch.setattr(compose, "font_faces", lambda brand: ("", set()))
    page = compose.basic_module(m, b, script_text="Title: T\n## One\nShow: A\nSay: First.")
    assert "fonts.googleapis.com" in page
    def fetch(url, ua=False):
        return b"@font-face{font-family:Inter;src:url(https://fonts.gstatic.com/s/inter.woff2) format('woff2')}" if "googleapis" in url else b"WOFF2DATA"
    out = compose.embed_fonts(page, fetch)
    assert "fonts.googleapis.com" not in out and "fonts.gstatic.com" not in out and "data:font/woff2;base64," in out
    assert compose.read_project(out)["edited"] is False                                          # still recognised as the Studio's own file
    assert compose.embed_fonts(page, lambda *a, **k: (_ for _ in ()).throw(OSError("offline"))) == page   # offline: unchanged


def test_the_players_own_elements_do_not_collide_with_the_motion_kit():
    """The kit's .count class counts up with a pseudo-element; the player's step counter must not use it."""
    page = compose.basic_module(parse("Title: T\n## One\nShow: A\nSay: First."), brand())
    bar = page[page.index('<div id="bar">'):page.index('<script type="application/json" id="html2mp4-source">')]
    assert 'class="count"' not in bar and 'class="pos"' in bar


FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def test_refresh_player_leaves_a_current_module_alone():
    m = parse("Title: T\n## One\nShow: A\nSay: First.")
    page = compose.basic_module(m, brand(), script_text="Title: T\n## One\nShow: A\nSay: First.")
    assert compose.refresh_player(page) == page


@pytest.mark.parametrize("fixture", ["module_player_v1.html", "module_player_v2.html"])
def test_refresh_player_upgrades_older_modules_without_touching_the_slides(fixture):
    from html2mp4.cli import load_scenes
    old = (FIXTURES / fixture).read_text()
    new = compose.refresh_player(old)
    for ident in ('id="fs"', 'id="studiovoice"', 'id="notice"', "speechSynthesis", "h2m:player-js"):
        assert ident in new
    assert new.count('id="bar"') == 1 and new.count('id="capbox"') == 1 and new.count("var flat = []") == 1     # replaced, not added
    assert new.count('<section class="slide') == old.count('<section class="slide') and load_scenes(new) == load_scenes(old)
    assert compose.refresh_player(new) == new                                                                   # and again changes nothing


def test_a_refreshed_module_still_counts_as_unedited_and_a_changed_one_does_not():
    old = (FIXTURES / "module_player_v2.html").read_text()
    assert compose.read_project(old)["edited"] is False
    assert compose.read_project(compose.refresh_player(old))["edited"] is False                                 # bringing the player up to date isn't an edit
    assert compose.read_project(compose.refresh_player(old.replace("Welcome", "Hello", 1)))["edited"] is True


def test_refresh_player_ignores_files_it_did_not_make():
    foreign = "<html><body><div id='bar'>mine</div><script>var flat = [];</script></body></html>"
    assert compose.refresh_player(foreign) == foreign
