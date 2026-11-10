import json, re, threading
import pytest
from html2mp4 import ai, compose, config, design, projects, review, script, verify

SCRIPT = "Title: T\n## One\nShow: Alpha · Beta\nSay: First the alpha.\nSay: Then the beta.\n## Two\nSay: Second slide here."
SCRIPT6 = "Title: Six\n" + "\n".join(f"## Slide {i}\nSay: Sentence for slide {i}." for i in range(1, 7))


def slide(sid, html, css="", layout="custom"):
    return {"id": sid, "layout": layout, "summary": f"layout of {sid}", "html": html, "css": css}


def simple(sid, title=None):
    """A valid, minimal design for any slide."""
    return slide(sid, f'<h2 class="t-heading" data-c="0">{title or "Sentence for slide " + sid[1:]}</h2>')


GOOD_ONE = slide("s1", '<h2 class="t-heading" data-c="0">One</h2><div class="row"><div class="card t-lead" data-c="0" data-cue="alpha">Alpha</div><div class="card t-lead" data-c="1" data-cue="beta">Beta</div></div>')
BAD_ONE = slide("s1", '<h2 class="t-heading" data-c="0" style="font-size:37px">One</h2><div class="card t-lead" data-c="1">Beta</div>')   # off-scale type
GOOD_TWO = slide("s2", '<h2 class="t-heading" data-c="0">Second slide here</h2>')
NO_PROBLEMS = {"problems": []}


class FakeClaude:
    """Stands in for ai.structured. Calls may arrive in parallel and in any order, so it answers by what is asked:
    `designs[sid]` for a design or revision, `fixes[sid]` (a list, used in turn) for a fix, `critiques` (a list) for the review."""
    def __init__(self, designs=None, fixes=None, critiques=(), thoughts=()):
        self.designs, self.fixes, self.critiques, self.thoughts = designs or {}, {k: list(v) for k, v in (fixes or {}).items()}, list(critiques), thoughts
        self.requests, self.lock = [], threading.Lock()

    def __call__(self, system, content, schema, effort="medium", max_tokens=0, on_text=None, on_thinking=None):
        text = content if isinstance(content, str) else content[0]["text"]
        kind = "critique" if "problems" in schema["properties"] else "fix" if text.startswith("This slide has problems") else "revise" if "Feedback to apply" in text else "design"
        with self.lock: self.requests.append({"kind": kind, "system": system, "content": content, "effort": effort, "text": text})
        for t in self.thoughts:
            if on_thinking: on_thinking(t)
        if kind == "critique":
            with self.lock: answer = self.critiques.pop(0) if self.critiques else NO_PROBLEMS
        else:
            if kind == "fix": ids = re.findall(r"### (s\d+) \(layout", text)[:1]
            elif kind == "revise": ids = [x.strip() for x in re.search(r"from: ([^.]*)\.", text).group(1).split(",")]
            else: ids = [x.strip() for x in re.search(r"Return one entry for each of: ([^.]*)\.", text).group(1).split(",")]
            with self.lock:
                answer = {"slides": [(self.fixes[i].pop(0) if kind == "fix" else self.designs.get(i) or simple(i)) for i in ids]}
        if on_text: on_text(json.dumps(answer, separators=(",", ":")))
        class U: input_tokens, output_tokens = 1000, 500
        return answer, U()

    def of(self, kind): return [r for r in self.requests if r["kind"] == kind]


def system_text(request): return "\n".join(b["text"] for b in request["system"]) if isinstance(request["system"], list) else request["system"]


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "config" / "settings.json")
    monkeypatch.setattr(projects, "MODULES", tmp_path / "modules")


def brand(): return dict(config.DEFAULT_BRAND)


def test_design_fixes_what_the_checker_finds(monkeypatch):
    fake = FakeClaude({"s1": BAD_ONE, "s2": GOOD_TWO}, fixes={"s1": [GOOD_ONE]})
    monkeypatch.setattr(ai, "structured", fake)
    m = script.parse(SCRIPT)
    r = design.design(m, brand())
    assert [i for i in r["issues"] if i.severity == "error"] == []
    assert r["calls"] == 3 and r["cost"] > 0                          # design, one fix, design review
    fix = fake.of("fix")[0]
    assert "37px" in fix["text"] and "### s1" in fix["text"] and fix["effort"] == "low"
    assert any(b["type"] == "image" for b in fix["content"])          # with a screenshot
    assert compose.check(r["html"], m) == []


def test_prompt_carries_narration_steps_and_the_brand_in_the_cached_system_prompt(monkeypatch):
    b = brand(); b["palette"] = [{"name": "Cyan Spot", "hex": "#04D1FF", "group": "primary", "usage": ""}]; b["rules"] = ["Never recolour the logo."]
    fake = FakeClaude({"s1": GOOD_ONE, "s2": GOOD_TWO})
    monkeypatch.setattr(ai, "structured", fake)
    design.design(script.parse(SCRIPT), b, glossary={"banned": ["Old Name"], "approved": [], "pronunciations": {}}, reference="<style>.x{}</style>")
    req = fake.of("design")[0]
    assert "0: First the alpha." in req["text"] and "1: Then the beta." in req["text"] and "Exact on-screen text (use verbatim): “Alpha” | “Beta”" in req["text"]
    sys = system_text(req)
    assert "--c-cyan-spot: #04D1FF" in sys and "Never recolour the logo." in sys and "Old Name" in sys and "<reference>" in sys
    assert all(blk["cache_control"]["ttl"] == "1h" for blk in req["system"])          # stable across calls: cached


def test_revision_only_changes_the_requested_slides(monkeypatch):
    prev = {"s1": design._clean(GOOD_ONE), "s2": design._clean(GOOD_TWO)}
    changed = slide("s2", '<h2 class="t-heading" data-c="0">Second slide here</h2><p class="t-body" data-c="0">Added</p>')
    fake = FakeClaude({"s2": changed})
    monkeypatch.setattr(ai, "structured", fake)
    r = design.design(script.parse(SCRIPT), brand(), previous=prev, only=["s2"], feedback="Add a line")
    assert r["slides"]["s1"] == prev["s1"] and "Added" in r["slides"]["s2"]["html"]
    assert "Add a line" in fake.of("revise")[0]["text"] and "only for the slides that need to change, from: s2" in fake.of("revise")[0]["text"]


def test_unchanged_design_needs_no_claude_unless_asked(monkeypatch):
    prev = {"s1": design._clean(GOOD_ONE), "s2": design._clean(GOOD_TWO)}
    fake = FakeClaude()
    monkeypatch.setattr(ai, "structured", fake)
    r = design.design(script.parse(SCRIPT), brand(), previous=prev)
    assert r["calls"] == 0 and fake.requests == []


def test_rule_breaking_html_is_rejected_before_rendering(monkeypatch):
    evil = slide("s1", '<h2 class="t-heading" data-c="0">One</h2><script>alert(1)</script>')
    fake = FakeClaude({"s1": evil, "s2": GOOD_TWO}, fixes={"s1": [GOOD_ONE]})
    monkeypatch.setattr(ai, "structured", fake)
    r = design.design(script.parse(SCRIPT), brand())
    assert "<script>alert" not in r["html"] and "scripts aren't allowed" in fake.of("fix")[0]["text"]


def test_review_during_a_targeted_change_only_concerns_the_slides_in_scope(monkeypatch):
    prev = {"s1": design._clean(GOOD_ONE), "s2": design._clean(GOOD_TWO)}
    problems = {"problems": [
        {"slide": "s1", "severity": "must", "problem": "old issue on slide one", "fix": "x"},
        {"slide": "s2", "severity": "must", "problem": "issue on slide two", "fix": "y"}]}
    fixed = slide("s2", '<h2 class="t-heading" data-c="0">Second slide here</h2><p class="t-body" data-c="0">fixed</p>')
    fake = FakeClaude({"s2": GOOD_TWO}, fixes={"s2": [fixed]}, critiques=[problems])
    monkeypatch.setattr(ai, "structured", fake)
    r = design.design(script.parse(SCRIPT), brand(), previous=prev, only=["s2"], feedback="tweak")
    fix = fake.of("fix")
    assert len(fix) == 1 and "issue on slide two" in fix[0]["text"] and "old issue on slide one" not in fix[0]["text"]
    assert fix[0]["effort"] == "medium"                                # review fixes keep more thinking than mechanical ones
    assert r["slides"]["s1"] == prev["s1"] and "fixed" in r["slides"]["s2"]["html"]


# ---- speed: design later slides side by side, fix slides side by side

def test_batch_planning():
    ids = [f"s{i}" for i in range(1, 7)]
    assert design.plan_batches(ids) == [["s1", "s2"], ["s3"], ["s4"], ["s5"], ["s6"]]      # the look first, then four calls side by side
    assert design.plan_batches(ids[:3]) == [ids[:3]]                                       # short modules: one call
    assert design.plan_batches(ids, lead=0) == [["s1", "s2"], ["s3", "s4"], ["s5", "s6"]]  # a look already exists
    assert design.plan_batches([f"s{i}" for i in range(1, 11)])[1:] == [["s3", "s4"], ["s5", "s6"], ["s7", "s8"], ["s9", "s10"]]


def test_later_slides_are_designed_in_parallel_to_match_the_first_ones(monkeypatch):
    fake = FakeClaude()
    monkeypatch.setattr(ai, "structured", fake)
    r = design.design(script.parse(SCRIPT6), brand(), polish=False)
    designs = fake.of("design")
    assert [re.search(r"Return one entry for each of: ([^.]*)\.", d["text"]).group(1) for d in designs[:1]] == ["s1, s2"]
    assert len(designs) == 5 and set(r["slides"]) == {f"s{i}" for i in range(1, 7)}
    for later in designs[1:]:
        assert "Match their look and feel exactly" in later["text"] and "### s1" in later["text"] and "### s2" in later["text"]


def test_slides_with_problems_are_fixed_side_by_side_each_in_its_own_call(monkeypatch):
    bad = lambda sid: slide(sid, f'<h2 class="t-heading" data-c="0" style="font-size:37px">Sentence for slide {sid[1:]}</h2>')
    fake = FakeClaude({"s2": bad("s2"), "s4": bad("s4")}, fixes={"s2": [simple("s2")], "s4": [simple("s4")]})
    monkeypatch.setattr(ai, "structured", fake)
    r = design.design(script.parse(SCRIPT6), brand(), polish=False)
    fixes = fake.of("fix")
    assert len(fixes) == 2 and sorted(re.findall(r"### (s\d+) \(layout", f["text"])[0] for f in fixes) == ["s2", "s4"]
    assert all("### s3" not in f["text"] and f["effort"] == "low" for f in fixes)
    assert [i for i in r["issues"] if i.severity == "error"] == []


# ---- visibility: what Claude is doing

def test_activity_and_live_thinking_are_reported(monkeypatch):
    events, thoughts, steps = [], {}, []
    fake = FakeClaude({"s1": BAD_ONE, "s2": GOOD_TWO}, fixes={"s1": [GOOD_ONE]}, thoughts=["Considering how to lay out the cards"])
    monkeypatch.setattr(ai, "structured", fake)
    design.design(script.parse(SCRIPT), brand(), progress=lambda f, label: steps.append((f, label)),
                  activity=lambda kind, text: events.append((kind, text)), thought=lambda key, label, text: thoughts.update({key: text}))
    kinds = [k for k, _ in events]
    assert kinds[0] == "plan" and {"write", "check", "fix", "review", "done"} <= set(kinds)
    assert any("writing slide 1" in t and "layout of s1" in t for k, t in events if k == "write")          # the slide's plan, as it starts
    assert any(k == "check" and "found 1 problem" in t for k, t in events)
    assert any(k == "check" and "slide 1, step 1" in t and "37px" in t for k, t in events)                 # the actual finding, in plain words
    assert any("Considering how to lay out the cards" in v or v == "" for v in thoughts.values())
    fractions = [f for f, _ in steps]
    assert fractions == sorted(fractions) and fractions[-1] == 1.0                                          # progress never goes backwards


def test_the_worked_example_in_the_prompt_passes_every_check():
    m = script.parse("Title: T\n## Why feedback matters\nShow: Builds trust · Speeds up growth · Prevents surprises\n" + "\n".join("Say: " + t for t in design.EXAMPLE_NARRATION))
    page = compose.assemble(m, brand(), [("example", design.EXAMPLE_HTML)], design.EXAMPLE_CSS)
    r = verify.inspect(page, m, shots=False)
    assert [i for i in r["issues"] if i.severity == "error"] == [] and compose.check(page, m) == []
    assert verify.static_issues("s1", design.EXAMPLE_HTML, design.EXAMPLE_CSS) == []


def test_module_wide_review_problems_reach_every_slide():
    ids = ["s1", "s2", "s3"]
    probs = [{"slide": "all", "severity": "must", "problem": "headings are not Title Case", "fix": "capitalise"},
             {"slide": "s2", "severity": "must", "problem": "card too small", "fix": "bigger"},
             {"slide": "all", "severity": "nice", "problem": "slightly plain", "fix": "add colour"}]
    out = design.expand_module_wide(probs, ids)
    assert [p["slide"] for p in out if p["problem"].startswith("headings")] == ids        # a must-fix goes to every slide
    assert [p["slide"] for p in out if p["problem"] == "slightly plain"] == [""]          # a suggestion stays a note about the module
    assert [p["slide"] for p in out if p["problem"] == "card too small"] == ["s2"]


def test_a_module_wide_problem_is_fixed_in_every_slide(monkeypatch):
    fixed = lambda sid: slide(sid, f'<h2 class="t-heading" data-c="0">Fixed {sid}</h2>')
    problems = {"problems": [{"slide": "all", "severity": "must", "problem": "headings must be Title Case", "fix": "capitalise"}]}
    fake = FakeClaude(fixes={f"s{i}": [fixed(f"s{i}")] for i in range(1, 4)}, critiques=[problems])
    monkeypatch.setattr(ai, "structured", fake)
    r = design.design(script.parse("Title: T\n## A\nSay: One.\n## B\nSay: Two.\n## C\nSay: Three."), brand())
    assert len(fake.of("fix")) == 3 and all("Fixed" in r["slides"][f"s{i}"]["html"] for i in range(1, 4))
    assert [i for i in r["issues"] if i.severity == "error"] == []


def test_shared_conventions_are_in_the_prompt():
    for phrase in ("capitalisation rules", "quotation marks", "copy their conventions exactly"):
        assert phrase in design.SYSTEM


def test_design_quality_setting_sets_the_effort(monkeypatch):
    assert config.design_quality() == "balanced" and config.design_effort() == "medium"
    config.set_design_quality("thorough")
    assert config.design_quality() == "thorough" and config.design_effort() == "high"
    with pytest.raises(ValueError): config.set_design_quality("reckless")


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
    class U: input_tokens, output_tokens = 500, 200
    monkeypatch.setattr(ai, "structured", lambda *a, **k: ({"suggestions": s}, U()))
    found, cost = review.review("Welcome teh team. same")
    assert [x["quote"] for x in found] == ["teh team"] and cost > 0
    assert review.apply("Welcome teh team.", found[0]) == "Welcome the team."


def test_glossary_round_trip():
    assert config.glossary() == {"pronunciations": {}, "banned": [], "approved": []}
    config.set_glossary({"pronunciations": {"R&D": "R and D", " ": "x"}, "banned": ["Old", ""]})
    assert config.glossary()["pronunciations"] == {"R&D": "R and D"} and config.glossary()["banned"] == ["Old"]
