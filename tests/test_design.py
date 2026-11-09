import json
import pytest
from html2mp4 import ai, compose, config, design, projects, review, script, verify

SCRIPT = "Title: T\n## One\nShow: Alpha · Beta\nSay: First the alpha.\nSay: Then the beta.\n## Two\nSay: Second slide here."


def slide(sid, html, css="", layout="custom"):
    return {"id": sid, "layout": layout, "summary": "a layout", "html": html, "css": css}


GOOD_ONE = slide("s1", '<h2 class="t-heading" data-c="0">One</h2><div class="row"><div class="card t-lead" data-c="0" data-cue="alpha">Alpha</div><div class="card t-lead" data-c="1" data-cue="beta">Beta</div></div>')
BAD_ONE = slide("s1", '<h2 class="t-heading" data-c="0" style="font-size:37px">One</h2><div class="card t-lead" data-c="1">Beta</div>')   # off-scale type
GOOD_TWO = slide("s2", '<h2 class="t-heading" data-c="0">Second slide here</h2>')


class FakeClaude:
    """Stands in for ai.structured: returns queued answers and records what it was asked."""
    def __init__(self, *answers): self.answers, self.requests = list(answers), []

    def __call__(self, system, content, schema, effort="medium", max_tokens=0, on_text=None):
        self.requests.append((system, content, effort))
        class U: input_tokens, output_tokens = 1000, 500
        return self.answers.pop(0), U()


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "config" / "settings.json")
    monkeypatch.setattr(projects, "MODULES", tmp_path / "modules")


def brand(): return dict(config.DEFAULT_BRAND)


def test_design_fixes_what_the_checker_finds(monkeypatch):
    fake = FakeClaude({"slides": [BAD_ONE, GOOD_TWO]}, {"slides": [GOOD_ONE]}, {"problems": []})
    monkeypatch.setattr(ai, "structured", fake)
    m = script.parse(SCRIPT)
    r = design.design(m, brand())
    assert [i for i in r["issues"] if i.severity == "error"] == []
    assert r["calls"] == 3 and r["cost"] > 0                          # design, one fix round, design review
    first_fix = fake.requests[1][1]
    assert "37px" in first_fix[0]["text"] and "s1" in first_fix[0]["text"]      # the problem was reported by slide
    assert any(b["type"] == "image" for b in first_fix)                         # with a screenshot
    assert compose.check(r["html"], m) == []


def test_prompt_carries_narration_steps_palette_and_rules(monkeypatch):
    b = brand(); b["palette"] = [{"name": "Cyan Spot", "hex": "#04D1FF", "group": "primary", "usage": ""}]; b["rules"] = ["Never recolour the logo."]
    fake = FakeClaude({"slides": [GOOD_ONE, GOOD_TWO]}, {"problems": []})
    monkeypatch.setattr(ai, "structured", fake)
    design.design(script.parse(SCRIPT), b, glossary={"banned": ["Old Name"], "approved": [], "pronunciations": {}})
    text = fake.requests[0][1]
    assert "0: First the alpha." in text and "1: Then the beta." in text and "--c-cyan-spot: #04D1FF" in text
    assert "Never recolour the logo." in text and "Old Name" in text and "Exact on-screen text (use verbatim): “Alpha” | “Beta”" in text


def test_revision_only_changes_the_requested_slides(monkeypatch):
    prev = {"s1": design._clean(GOOD_ONE), "s2": design._clean(GOOD_TWO)}
    changed = slide("s2", '<h2 class="t-heading" data-c="0">Second slide here</h2><p class="t-body" data-c="0">Added</p>')
    fake = FakeClaude({"slides": [changed]}, {"problems": []})
    monkeypatch.setattr(ai, "structured", fake)
    r = design.design(script.parse(SCRIPT), brand(), previous=prev, only=["s2"], feedback="Add a line")
    assert r["slides"]["s1"] == prev["s1"] and "Added" in r["slides"]["s2"]["html"]
    assert "Add a line" in fake.requests[0][1] and "only for the slides that need to change, from: s2" in fake.requests[0][1]


def test_unchanged_design_needs_no_claude_unless_asked(monkeypatch):
    prev = {"s1": design._clean(GOOD_ONE), "s2": design._clean(GOOD_TWO)}
    monkeypatch.setattr(ai, "structured", FakeClaude())             # any call would fail: no answers queued
    r = design.design(script.parse(SCRIPT), brand(), previous=prev)
    assert r["calls"] == 0 and r["issues"] == [] or all(i.severity != "error" for i in r["issues"])


def test_rule_breaking_html_is_rejected_before_rendering(monkeypatch):
    evil = slide("s1", '<h2 class="t-heading" data-c="0">One</h2><script>alert(1)</script>')
    fake = FakeClaude({"slides": [evil, GOOD_TWO]}, {"slides": [GOOD_ONE]}, {"problems": []})
    monkeypatch.setattr(ai, "structured", fake)
    r = design.design(script.parse(SCRIPT), brand())
    assert "<script>alert" not in r["html"] and "scripts aren't allowed" in fake.requests[1][1][0]["text"]


# ---- projects and script review

def test_project_versions_and_restore():
    p = projects.create("My Module", "script one")
    projects.save_version(p["id"], "<html>v1</html>", {"s1": {"layout": "a"}}, "First design", cost=0.5)
    projects.save_version(p["id"], "<html>v2</html>", {"s1": {"layout": "b"}}, "Feedback", script_text="script two")
    assert projects.get(p["id"])["current"] == 2 and projects.slides(p["id"])["s1"]["layout"] == "b"
    projects.restore(p["id"], 1)
    q = projects.get(p["id"])
    assert q["current"] == 3 and q["script"] == "script one" and q["versions"][-1]["note"] == "Restored version 1"
    assert projects.version_html(p["id"], 3) == "<html>v1</html>" and len(projects.listing()) == 1
    assert projects.create("My Module", "x")["id"] == "My-Module-2"


def test_review_only_keeps_suggestions_that_match_the_script(monkeypatch):
    s = [{"kind": "typo", "quote": "teh team", "replacement": "the team", "reason": "typo"},
         {"kind": "typo", "quote": "not in script", "replacement": "x", "reason": "made up"},
         {"kind": "risk", "quote": "same", "replacement": "same", "reason": "no change"}]
    monkeypatch.setattr(ai, "structured", FakeClaude({"suggestions": s}))
    found, cost = review.review("Welcome teh team. same")
    assert [x["quote"] for x in found] == ["teh team"] and cost > 0
    assert review.apply("Welcome teh team.", found[0]) == "Welcome the team."


def test_glossary_round_trip():
    assert config.glossary() == {"pronunciations": {}, "banned": [], "approved": []}
    config.set_glossary({"pronunciations": {"R&D": "R and D", " ": "x"}, "banned": ["Old", ""]})
    assert config.glossary()["pronunciations"] == {"R&D": "R and D"} and config.glossary()["banned"] == ["Old"]


def test_review_during_a_targeted_change_only_concerns_the_slides_in_scope(monkeypatch):
    prev = {"s1": design._clean(GOOD_ONE), "s2": design._clean(GOOD_TWO)}
    problems = {"problems": [
        {"slide": "s1", "severity": "must", "problem": "old issue on slide one", "fix": "x"},
        {"slide": "s2", "severity": "must", "problem": "issue on slide two", "fix": "y"}]}
    fixed = slide("s2", '<h2 class="t-heading" data-c="0">Second slide here</h2><p class="t-body" data-c="0">fixed</p>')
    fake = FakeClaude({"slides": [GOOD_TWO]}, problems, {"slides": [fixed]}, {"problems": []})
    monkeypatch.setattr(ai, "structured", fake)
    r = design.design(script.parse(SCRIPT), brand(), previous=prev, only=["s2"], feedback="tweak")
    fix_request = fake.requests[2][1][0]["text"]
    assert "issue on slide two" in fix_request and "old issue on slide one" not in fix_request
    assert r["slides"]["s1"] == prev["s1"] and "fixed" in r["slides"]["s2"]["html"]
