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


# ---- the "Scene N / On screen / paragraph" format ----

from html2mp4.script import split_sentences

SCENES = """One micro-learning: How to Interview Candidates
About 6 minutes.
Scene 1: The opening (0:00 to 0:30)
On screen: “Every hire shapes the team.”
Think back to the best colleague. What made them the best? Our job is to find people like that.
Scene 2: What we’re looking for (0:30 to 1:30)
On screen: four labels appear in turn: Curious. Owns the work.
They’re curious, so they look past the task. And they’re honest. One interviewer says: “If they know, they’ll tell you. If they don’t, they’ll say so.”
"""


def test_scene_format():
    m = parse(SCENES)
    assert m.title == "How to Interview Candidates" and m.subtitle == "About 6 minutes."
    assert [s.title for s in m.slides] == ["The opening", "What we’re looking for"]
    assert m.slides[0].timing == "0:00 to 0:30"
    assert m.slides[0].screen == "“Every hire shapes the team.”" and m.slides[0].show == ["Every hire shapes the team."]
    assert m.slides[1].show == [] and m.slides[1].screen.startswith("four labels")
    assert m.slides[0].say == ["Think back to the best colleague.", "What made them the best?", "Our job is to find people like that."]
    assert m.intro == []


def test_sentence_split_keeps_quotes_and_abbreviations_together():
    assert split_sentences("He is honest. She left. Okay.") == ["He is honest.", "She left.", "Okay."]      # "honest." is not "St."
    assert split_sentences("Use tools, e.g. Python. Then stop.") == ["Use tools, e.g. Python.", "Then stop."]
    assert split_sentences("One says: “If they know, they’ll tell you. If not, they’ll say so.” Done.") == [
        "One says: “If they know, they’ll tell you. If not, they’ll say so.”", "Done."]
    assert split_sentences("Version 2.5 is out. Great.") == ["Version 2.5 is out.", "Great."]


def test_scene_without_narration_is_an_error():
    with pytest.raises(ScriptError, match="has no narration"):
        parse("My title\nScene 1: Empty\nOn screen: nothing")
