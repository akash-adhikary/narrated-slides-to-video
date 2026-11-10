import os, stat
import pytest
from html2mp4 import config


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_defaults_without_a_file():
    assert config.brand() == config.DEFAULT_BRAND
    assert config.api_key_status() == {"set": False, "source": None, "masked": None}


def test_saved_key_wins_and_file_is_private(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-environment-1234")
    assert config.api_key_status()["source"] == "environment"
    config.set_api_key("  sk-ant-saved-key-abcdefgh  ")
    assert config.api_key() == "sk-ant-saved-key-abcdefgh"
    assert config.api_key_status() == {"set": True, "source": "settings", "masked": "sk-ant-…efgh"}
    assert stat.S_IMODE(os.stat(config.SETTINGS_FILE).st_mode) == 0o600
    config.clear_api_key()
    assert config.api_key_status()["source"] == "environment"


def test_brand_validation():
    b = config.update_brand({"accent": "#123abc", "footer_text": "x" * 200, "unknown": 1, "logo": "ignored"})
    assert b["accent"] == "#123abc" and len(b["footer_text"]) == 80 and "unknown" not in b and b["logo"] == ""
    for bad in ({"accent": "red"}, {"heading_font": "Comic Sans"}, {"style": "neon"}):
        with pytest.raises(ValueError):
            config.update_brand(bad)
    assert config.reset_brand() == config.DEFAULT_BRAND


def test_fresh_install_starts_with_the_bundled_thoughtspot_brand(tmp_path, monkeypatch):
    monkeypatch.delenv("HTML2MP4_BRAND", raising=False)
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path); monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    b = config.brand()
    assert (b["background"], b["heading_font"], b["body_font"]) == ("#08062B", "Geist Mono", "Geist")
    assert b["logo_on_dark"].startswith("data:image/svg") and b["palette"] and b["rules"] and not b["reference"]
    assert {"Geist", "Geist Mono"} <= set(config.available_fonts()) and (tmp_path / "fonts" / "Geist-VariableFont_wght.ttf").exists()
    assert config.glossary()["pronunciations"]["R&D"] == "R and D"
    assert "anthropic_api_key" not in (config.BUNDLED / "brand.json").read_text()


def test_saved_brand_wins_over_the_bundled_default_and_reset_returns_to_it(tmp_path, monkeypatch):
    monkeypatch.delenv("HTML2MP4_BRAND", raising=False)
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path); monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    config.update_brand({"accent": "#112233"})
    assert config.brand()["accent"] == "#112233" and config.brand()["background"] == "#08062B"
    config.set_glossary({"pronunciations": {"X": "ex"}})
    assert config.glossary()["pronunciations"] == {"X": "ex"}
    assert config.reset_brand()["accent"] == "#04D1FF"
