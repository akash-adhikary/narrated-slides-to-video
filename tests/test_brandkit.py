import io, json, zipfile
import pytest
from html2mp4 import brandkit, compose, config
from html2mp4.script import EXAMPLE, parse


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "config" / "settings.json")
    monkeypatch.setattr(brandkit, "STAGING", tmp_path / "staging")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def svg(fill):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 28"><rect width="120" height="28" fill="{fill}"/></svg>'.encode()


def font(family):
    """A tiny but valid TrueType font with the given family name."""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder([".notdef", "A"]); fb.setupCharacterMap({65: "A"})
    pen = TTGlyphPen(None); pen.moveTo((0, 0)); pen.lineTo((500, 700)); pen.lineTo((1000, 0)); pen.closePath()
    fb.setupGlyf({".notdef": TTGlyphPen(None).glyph(), "A": pen.glyph()})
    fb.setupHorizontalMetrics({".notdef": (500, 0), "A": (1000, 0)}); fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": family, "styleName": "Regular"}); fb.setupOS2(usWeightClass=400); fb.setupPost()
    buf = io.BytesIO(); fb.save(buf); return buf.getvalue()


MODULE = """<html><style>:root{ --dark:#0B1020; --sky:#2BB3FF; --paper:#FFFFFF; --mint:#38D39F;
  --head:"Acme Sans", sans-serif; }</style><body>
<script>var scenes = [{id:'s0', chunks:["Hi."]}];</script></body></html>"""


def kit_files():
    return [("Acme Brand/Logos/acme_logo_white.svg", svg("#FFFFFF")),
            ("Acme Brand/Logos/acme_logo_black.svg", svg("#000000")),
            ("Acme Brand/Logos/acme_icon_white.svg", svg("#FFFFFF")),
            ("Acme Brand/Fonts/AcmeSans-Regular.ttf", font("Acme Sans")),
            ("Acme Brand/.DS_Store", b"junk"),
            ("old-module.html", MODULE.encode())]


def test_analyze_without_ai():
    p = brandkit.analyze(kit_files())
    assert p["kit_name"] == "Acme Brand"
    assert p["sources"] == {"pdf": False, "logos": 3, "fonts": 1, "module": True, "ai": False}
    assert [c["hex"] for c in p["palette"]] == ["#0B1020", "#2BB3FF", "#FFFFFF", "#38D39F"]
    assert p["dark"]["background"] == "#0B1020" and p["light"]["background"] == "#FFFFFF"
    assert p["fonts"][0]["family"] == "Acme Sans" and "Acme Sans" in p["font_names"]
    by = {l["id"]: l for l in p["logos"]}
    assert by[p["logo_on_dark"]]["name"] == "acme_logo_white.svg"       # primary beats icon
    assert by[p["logo_on_light"]]["name"] == "acme_logo_black.svg"
    assert p["reference"]["name"] == "old-module.html"


def test_zip_is_unpacked():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in kit_files(): z.writestr(name, data)
        z.writestr("__MACOSX/Acme Brand/._x.svg", b"junk")
    p = brandkit.analyze([("acme.zip", buf.getvalue())])
    assert p["sources"]["logos"] == 3 and p["sources"]["fonts"] == 1


def test_apply_installs_fonts_logos_and_reference():
    p = brandkit.analyze(kit_files())
    b = brandkit.apply(p["id"], {"style": "dark", "accent": "#38D39F", "heading_font": "Acme Sans", "body_font": "Acme Sans"})
    assert b["background"] == "#0B1020" and b["accent"] == "#38D39F" and b["heading_font"] == "Acme Sans"
    assert b["logo_on_dark"].startswith("data:image/svg+xml") and b["logo_on_light"].startswith("data:image/svg+xml")
    assert "Acme Sans" in config.available_fonts()
    assert brandkit.reference_file().exists() and b["reference"] == "old-module.html"
    page = compose.basic_module(parse(EXAMPLE), b)
    assert '@font-face{font-family:"Acme Sans"' in page and "fonts.googleapis" not in page
    assert compose.check(page, parse(EXAMPLE)) == []
    b = brandkit.remove_kit()
    assert b["palette"] == [] and b["reference"] == "" and not brandkit.reference_file().exists()


def test_nothing_usable_and_expired_proposal():
    p = brandkit.analyze([("notes.txt", b"hello")])
    assert not (p["palette"] or p["logos"] or p["fonts"])
    with pytest.raises(ValueError, match="expired"):
        brandkit.apply("doesnotexist", {})


def test_contrast_helpers():
    assert round(brandkit.contrast("#000000", "#FFFFFF")) == 21
    assert brandkit.logo_tone("logo_reverse.png", b"") == "light"
