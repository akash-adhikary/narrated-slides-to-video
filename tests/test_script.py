import pytest
from html2mp4.script import EXAMPLE, ScriptError, parse


def test_example_parses():
    m = parse(EXAMPLE)
    assert m.title == "Giving Feedback That Lands"
    assert m.subtitle == "Manager Essentials · Module 2"
    assert m.intro == ["Welcome to module two of Manager Essentials."]
    assert [s.title for s in m.slides] == ["Why feedback matters", "The SBI model", "Your next step"]
    assert m.slides[0].show == ["Builds trust", "Speeds up growth", "Prevents surprises"]
    assert m.slides[1].note == "three steps, left to right"
    assert m.sentences == 7


def test_bullets_continuations_and_comments():
    m = parse("""# My module
## One
- first point
- second point
  that wraps
// a comment
Say: A sentence that
continues here.
Say: Second.""")
    assert m.title == "My module"
    assert m.slides[0].show == ["first point", "second point that wraps"]
    assert m.slides[0].say == ["A sentence that continues here.", "Second."]


def test_narration_kept_verbatim():
    text = 'Say: She said "it\'s fine" — then left; 3 < 4 & </script>!'
    m = parse(f"Title: T\n## S\n{text}")
    assert m.slides[0].say == [text[5:]]


def test_title_override():
    m = parse("## S\nSay: Hi.", title="From CSV", subtitle="Sub")
    assert (m.title, m.subtitle) == ("From CSV", "Sub")


@pytest.mark.parametrize("text, message", [
    ("## S\nSay: hi", "needs a title"),
    ("Title: T", "has no slides"),
    ("Title: T\n## S\nShow: a", "has no narration"),
    ("Title: T\n## S\nSay:", "has no text"),
    ("Title: T\nShow: x", "belongs under"),
    ("Title: T\nrandom words", "not sure what this is"),
    ("Title: T\n## S\nSay: a\nTitle: again", "goes at the top"),
])
def test_errors(text, message):
    with pytest.raises(ScriptError, match=message):
        parse(text)
