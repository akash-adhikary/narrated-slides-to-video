import os

# Tests assume the plain neutral brand unless a test opts in to the bundled ThoughtSpot default.
os.environ.setdefault("HTML2MP4_BRAND", "neutral")

import pytest


@pytest.fixture(autouse=True)
def _own_media_library(tmp_path, monkeypatch):
    """Every test gets an empty media library of its own: tests never read or write the real one."""
    from html2mp4 import media
    monkeypatch.setattr(media, "MEDIA", tmp_path / "media-library")
