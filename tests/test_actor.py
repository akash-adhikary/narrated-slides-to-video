"""A character that speaks and acts on cue (Spotter): the script words for it, its voice, what it can do, how the page plays it and how the video
renders it, and that scripts without a character are exactly as they were."""
import json, re
import numpy as np
import pytest
from PIL import Image
from playwright.sync_api import sync_playwright
from html2mp4 import cli, compose, config, design, media, script
from test_studio import client, wait   # noqa: F401


# ---------------------------------------------------------------- a small actor for the tests

def sprite(speaker="Spotter", name="Spotter", voice="Puppy"):
    idle = [Image.new("RGBA", (60, 80), (200, 170, 60, 255)) for _ in range(4)]; talk = [Image.new("RGBA", (60, 80), (200, 60, 60, 255)) for _ in range(4)]
    data, w, h = media._sprite_rows([idle, talk])
    return media._store(data, "webp", w, h, True, name, "mascot", "", None, "test", {"frames": 4, "fps": 12, "mode": "character", "rows": 2},
                        {"speaker": speaker, **({"voice": voice} if voice else {})})


def clip(name, seconds=0.5, color=(30, 160, 220, 255)):
    n = max(2, round(seconds * 12)); data, w, h = media._encode_webm([Image.new("RGBA", (60, 80), color) for _ in range(n)], 12, True)
    return media._store(data, "webm", w, h, True, name, "mascot", "", None, "test", None, {"seconds": round(n / 12, 2), "fps": 12, "poster": 0})


def actor(*actions):
    ch = sprite()
    for a in actions: media.link_action(ch["id"], a, clip(f"clip {a}", 0.5 if a != "wink" else 0.7)["id"])
    return media.get(ch["id"])


SLIDE = '<h2 class="t-heading" data-c="0">Hello</h2><div data-c="0" style="width:300px"><img data-asset="spotter" alt="Spotter"></div>'


def page(text, slides=None):
    m = script.parse(text)
    return m, compose.assemble(m, config.brand(), slides or [("custom", SLIDE)] * len(m.slides), "", motion="calm")


# ---------------------------------------------------------------- the words of a script

def test_a_character_is_addressed_in_several_ways():
    t = '''Meet the team
Voice: Spotter = Puppy
Scene 1: Hello (0:00–0:10)
Narration: "Welcome aboard. Here is our guide."
Spotter animate: wave
Spotter say: "Hi, I'm Spotter!
I find answers."
Spotter speak Ask me anything.
Spotter bubble: Printed words.
Spotter: animate wag his tail then wink
Spotter perform: jump
Spotter: This is the old way of speaking.
Visual: a dog
'''
    m = script.parse(t); s = m.slides[0]
    assert m.voices == {"Spotter": "am_puck|6|1.1"}
    assert list(zip(s.say, s.speakers)) == [("Welcome aboard.", ""), ("Here is our guide.", ""), ("Hi, I'm Spotter!", "Spotter"), ("I find answers.", "Spotter"),
                                            ("Ask me anything.", "Spotter"), ("Printed words.", "Spotter"), ("This is the old way of speaking.", "Spotter")]
    assert s.shown == [5]                                                # only the bubble is printed
    assert [(a["at"], a["do"]) for a in s.acts] == [(2, "wave"), (6, "wag his tail then wink"), (6, "jump")]
    assert s.cast() == ["Spotter"]
    for verb in ("caption", "print", "write", "type"):
        assert script.parse(f"Title: T\nVoice: Max = Heart\n## A\nSay: Hi.\nMax {verb}: Words.\n").slides[0].shown == [1]
    for verb in ("says", "speaks"):
        assert script.parse(f"Title: T\nVoice: Max = Heart\n## A\nSay: Hi.\nMax {verb}: Words.\n").slides[0].speakers == ["", "Max"]
    s2 = script.parse("Title: T\nVoice: Max = Heart\n## A\nSay: Hi.\nMax animate wave\nMax act: nod\nMax: animate shake his head\n").slides[0]
    assert [a["do"] for a in s2.acts] == ["wave", "nod", "shake his head"] and s2.speakers == []


def test_a_character_appears_by_being_used_and_never_hijacks_narration():
    m = script.parse("Title: T\n## A\nSay: Hello.\nSpotter say: Hi there.\nSpotter animate: wave\n")           # no declaration: using the character is enough
    assert m.voices == {"Spotter": None} and m.slides[0].speakers == ["", "Spotter"] and m.slides[0].acts[0]["who"] == "Spotter"
    n = script.parse("Title: T\n## A\nSay: Spotter says that data matters.\nSay: Spotter say what you think.\n")  # narration that merely begins with the name
    assert n.voices == {} and n.slides[0].speakers == [] and n.slides[0].acts == []
    scenes = 'Intro\nScene 1: A\nNarration: "Spotter says that data matters. Voice: this is narration."\nVoice: Welcome to the module\n'
    k = script.parse(scenes)
    assert k.voices == {} and "Voice: Welcome to the module" in " ".join(k.slides[0].say)                     # an old "Voice:" line is narration, as it always was
    with pytest.raises(script.ScriptError, match="nothing after it"): script.parse("Title: T\nVoice: Max = Heart\n## A\nSay: Hi.\nMax animate:\n")
    with pytest.raises(script.ScriptError, match="no voice called"): script.parse("Title: T\nVoice: Max = Gandalf\n## A\nSay: Hi.\n")
    with pytest.raises(script.ScriptError, match="narrator's voice"): script.parse("Title: T\nVoice: Narrator = Heart\n## A\nSay: Hi.\n")


def test_scripts_without_a_character_are_exactly_as_before():
    legacy = ["Title: T\nSubtitle: S\nSay: Welcome.\n\n## One\nShow: A · B\nNote: two cards\nHold: 2\nSay: First.\nSay: Second.\n",
              "One micro-learning: How to interview\nScene 1: The opening (0:00 to 0:30)\nOn screen: \"Every hire shapes the team.\"\nThink back to the best colleague. What made them the best?\nNarration: \"Second paragraph. Two sentences.\"\n"]
    for t in legacy:
        m = script.parse(t); d = m.to_dict()
        assert d["voices"] == {} and d["intro_speakers"] == [] and d["intro_acts"] == [] and d["intro_shown"] == []
        assert all(s["speakers"] == [] and s["acts"] == [] and s["shown"] == [] for s in d["slides"])
        _, p = page(t)
        assert 'id="h2m-cast"' not in p and "var voices" not in p and "who:" not in p and "h2m-pic-" not in p


# ---------------------------------------------------------------- voices

def test_a_voice_is_a_base_voice_lifted_and_quickened():
    assert script.voice_id("Puppy") == "am_puck|6|1.1" and script.voice_id("puppy") == "am_puck|6|1.1" and script.voice_id("Pup High") == "am_puck|8|1.12"
    assert script.voice_id("Puck") == "am_puck" and script.voice_id("am_puck") == "am_puck" and script.voice_id("Heart") == "af_heart"
    assert script.voice_id("Puck, pitch +4, pace 1.2") == "am_puck|4|1.2" and script.voice_id("Puck +3") == "am_puck|3|1" and script.voice_id("Puppy, pace 0.9") == "am_puck|6|0.9"
    assert cli.split_voice("am_puck|6|1.1") == ("am_puck", 6.0, 1.1) and cli.split_voice("af_heart") == ("af_heart", 0.0, 1.0)
    assert cli.join_voice("af_heart") == "af_heart" and cli.join_voice("am_puck", -2, 1) == "am_puck|-2|1"
    with pytest.raises(script.ScriptError, match="pace"): script.voice_id("Puck, pace 5")
    assert cli.clip_path("Hi.", "am_puck|6|1.1", 0.9, __import__("pathlib").Path("/c")).name.startswith("am_puck@6@1.1_0.9_")      # a filename any system accepts


def test_lifting_a_voice_raises_its_pitch_and_keeps_its_length():
    sr = 24000; t = np.arange(sr) / sr; tone = (0.4 * np.sin(2 * np.pi * 150 * t)).astype(np.float32)
    up = cli.pitch_shift(tone, 12, sr)
    assert abs(len(up) - len(tone)) < 0.03 * sr
    freq = lambda a: np.argmax(np.abs(np.fft.rfft(a[:sr] * np.hanning(min(len(a), sr)))[50:800])) + 50
    assert abs(freq(up) - 300) < 12 and abs(freq(cli.pitch_shift(tone, -12, sr)) - 75) < 8
    assert cli.pitch_shift(tone, 0, sr) is tone


def test_each_sentence_is_voiced_by_its_speaker_with_the_speakers_pitch_and_pace(tmp_path, monkeypatch):
    calls = []
    class Piece:
        def __init__(self, a): self.audio = a; self.tokens = []
    def fake_pipe(text, voice, speed):
        calls.append((text, voice, round(speed, 3))); return [Piece(np.full(24000, 0.2, np.float32))]
    monkeypatch.setattr(cli, "kokoro_pipeline", lambda lang: fake_pipe)
    scenes = [{"id": "s1", "chunks": ["Narrator line.", "Spotter line."], "who": {1: "Spotter"}, "voices": {1: "am_puck|6|1.1"}}]
    audio = cli.synthesize(scenes, "af_heart", 0.9, tmp_path)
    assert ("Narrator line.", "af_heart", 0.9) in calls and ("Spotter line.", "am_puck", 0.99) in calls          # 0.9 x 1.1
    assert len(audio[0]) == 2 and abs(len(audio[0][1]) - 24000) < 1500                                             # lifted, but the same length
    assert cli.pending(scenes, "af_heart", 0.9, tmp_path) == 0


# ---------------------------------------------------------------- what a character can do

def test_the_words_of_an_action_are_matched_by_meaning():
    motions = list(media.MOTIONS); clips = motions + ["wave", "wink", "laugh", "wag", "think"]
    m = lambda text, have=clips: media.match_actions(text, have)
    assert m("wave") == ["wave"] and m("say hello with a wave") == ["wave"] and m("laugh out loud") == ["laugh"] and m("giggle") == ["laugh"]
    assert m("wiggle his tail") == ["wag"] and m("wiggle his tail", motions) == ["wiggle"]                     # a clip of the character beats a loose motion
    assert m("wink and jump") == ["wink", "jump"] and m("jump then nod then wave") == ["jump", "nod", "wave"] and len(m("jump hop nod shake wave wink")) == 3
    assert m("do a little dance", motions) == ["bounce"] and m("moonwalk") == [] and m("") == []
    assert m("WAVE!") == ["wave"] and m("he waves hello") == ["wave"]


def test_what_a_script_makes_a_character_do_is_resolved_against_the_library():
    actor("wave", "wink")
    m = script.parse("Title: T\nVoice: Spotter = Puppy\n## A\nSay: One.\nSpotter animate: wave\nSay: Two.\nSpotter animate: jump, then wink\nSpotter animate: moonwalk\nSpotter animate: wiggle\n"
                     "## B\nSay: Three.\nSpotter say: Hi.\nSpotter animate: wave\n")
    c = media.cast_for(m)
    assert c["acts"] == {"s1": {"1": [["Spotter", "wave"]], "2": [["Spotter", "jump"], ["Spotter", "wink"], ["Spotter", "wiggle"]]}, "s2": {"2": [["Spotter", "wave"]]}}
    assert c["unknown"] == [("s1", "Spotter", "moonwalk")]
    a = c["actors"]["Spotter"]["actions"]
    assert a["wave"]["kind"] == "clip" and a["jump"]["kind"] == "motion" and a["wink"]["seconds"] == 0.67 and a["jump"]["seconds"] == media.MOTIONS["jump"]
    assert c["clips"] == {"Spotter": {"wave", "wink"}} and c["by_slide"] == {"s1": {"Spotter": {"wave", "wink"}}, "s2": {"Spotter": {"wave"}}}
    assert media.cast_for(script.parse("Title: T\n## A\nSay: Hello.\n"))["acts"] == {}                         # nothing acts: nothing to embed


def test_a_clip_becomes_an_action_whole_or_in_part_and_can_be_taken_away():
    ch = sprite(); c = clip("A clip", 1.2)
    media.link_action(ch["id"], "  Wave!! ", c["id"])
    assert media.get(ch["id"])["actions"] == {"wave": c["id"]} and media.actions_of(media.get(ch["id"]))["wave"] == c["seconds"]
    part = media.link_action(ch["id"], "short", c["id"], 0.2, 0.7)["actions"]["short"]
    assert part != c["id"] and 0.4 < media.get(part)["seconds"] < 0.6 and media.get(part)["transparent"]          # a part is a new clip of its own
    media.unlink_action(ch["id"], "wave"); assert "wave" not in media.get(ch["id"]).get("actions", {})
    media.delete(part); assert "short" not in media.actions_of(media.get(ch["id"]))                              # a deleted clip is no longer an action
    with pytest.raises(media.MediaError, match="name"): media.link_action(ch["id"], "!!", c["id"])
    with pytest.raises(media.MediaError, match="video clip"): media.link_action(ch["id"], "x", ch["id"])
    with pytest.raises(media.MediaError, match="talking character"): media.link_action(c["id"], "x", c["id"])


def test_a_green_screen_clip_is_cut_out_in_the_frame_of_its_character():
    def green(offset, w=160, h=120):
        fr = []
        for k in range(12):
            a = np.zeros((h, w, 3), np.uint8); a[:] = (40, 230, 40); x = 50 + offset + k; a[40:100, x:x + 40] = (235, 215, 180)
            fr.append(Image.fromarray(a).convert("RGBA"))
        d, ww, hh = media._encode_webm(fr, 12, False)
        return media._store(d, "webm", ww, hh, False, f"green {offset}", "mascot", "", None, "t", None, {"seconds": 1.0, "fps": 12, "poster": 0, "speech": []})
    base = green(0); cut = media.edit(base["id"], "remove_background", {}, name="cut")
    assert cut["transparent"] and cut["crop"] and cut["frame"] == [160, 120] and media.green_screen_colour(Image.new("RGB", (9, 9), (40, 230, 40)))
    sp = sprite(); items = media.listing(); next(i for i in items if i["id"] == sp["id"]).update(parent=cut["id"]); media._save(items)
    media.link_action(sp["id"], "dance", green(2)["id"], 0.0, 0.8)
    act = media.get(media.get(sp["id"])["actions"]["dance"])
    assert act["crop"] == cut["crop"] and act["frame"] == cut["frame"] and act["transparent"]                    # the same frame, so nothing shifts on screen
    first = media.video_frames(act, 0, 0.2, 12)[0]; assert first.size == (cut["crop"][2] - cut["crop"][0], cut["crop"][3] - cut["crop"][1])
    with pytest.raises(media.MediaError, match="outside the frame"):
        media.link_action(sp["id"], "far", green(70)["id"], 0.0, 0.8)                                            # it leaves the frame the character was cut in
    assert media.frame_around((10, 10, 50, 60), (30, 5, 90, 70), size=(200, 100), margin=0.0) == (10, 5, 90, 70)
    assert media.frame_around((10, 10, 50, 60), size=(200, 100), margin=0.0, side_room=0.1) == (0, 10, 70, 60)


def test_a_character_has_a_voice_of_its_own_in_the_library():
    ch = sprite(voice="")
    assert media.actor_voice("spotter") is None and media.actor("SPOTTER")["id"] == ch["id"]                      # found whatever the capitals
    media.update(ch["id"], voice="Pup High"); assert media.actor_voice("Spotter") == "Pup High"
    media.update(ch["id"], voice=""); assert media.actor_voice("Spotter") is None
    with pytest.raises(media.MediaError, match="no voice called"): media.update(ch["id"], voice="Gandalf")
    still = media.add(_png(), "Still.png"); media.update(still["id"], speaker="Spotter")
    assert media.actor("Spotter")["id"] == ch["id"]                                                               # only a talking character counts


def _png():
    import io; b = io.BytesIO(); Image.new("RGBA", (40, 40), (200, 30, 30, 255)).save(b, "PNG"); return b.getvalue()


def test_the_assistant_is_told_what_each_character_can_do():
    actor("wave"); text = media.catalog_text()
    assert "speaks as Spotter" in text and "who can:" in text and "wave" in text and "jump" in text


# ---------------------------------------------------------------- the page

def test_the_page_carries_the_cast_each_slides_clips_and_each_picture_once():
    actor("wave", "wink")
    t = "Title: T\nVoice: Spotter = Puppy\n## A\nSay: One.\nSpotter animate: wave\nSay: Two.\n## B\nSay: Three.\nSpotter say: Hi.\n## C\nSay: Four.\nSpotter animate: wink\nSpotter animate: jump\n"
    m, p = page(t)
    cast = json.loads(re.search(r'<script type="application/json" id="h2m-cast">(.*?)</script>', p, re.S).group(1))
    assert cast["acts"] == {"s1": {"1": [["Spotter", "wave"]]}, "s3": {"1": [["Spotter", "wink"], ["Spotter", "jump"]]}}
    assert cast["actors"]["Spotter"]["actions"]["wave"] == {"kind": "clip", "seconds": 0.5} and cast["actors"]["Spotter"]["actions"]["jump"]["kind"] == "motion"
    sections = dict(re.findall(r'<section class="slide [^"]*" id="(s\d)">(.*?)</section>', p, re.S))
    assert re.findall(r'data-act="(\w+)"', sections["s1"]) == ["wave"] and sections["s2"].count("<video") == 0 and re.findall(r'data-act="(\w+)"', sections["s3"]) == ["wink"]
    assert 'class="h2m-actor' in sections["s1"] and 'class="h2m-sprite h2m-char h2m-pic-spotter" data-speaker="Spotter"' in sections["s1"]
    assert p.count(".h2m-pic-spotter{background-image:url(data:image/webp;base64,") == 1 and "background-image:url(data:image/webp" not in "".join(sections.values())   # the picture once
    assert 'class="h2m-sprite h2m-char h2m-pic-spotter" data-speaker="Spotter"' not in sections["s2"] and 'class="h2m-sprite h2m-char h2m-pic-spotter"' in sections["s2"]   # a character with no clips is a plain picture
    assert compose.check(p, m) == [] and cli.load_scenes(p)[0]["acts"] == {1: [("Spotter", "wave", "clip", 0.5)]}


# ---------------------------------------------------------------- the video's timeline

def audio(*seconds): return [np.zeros(int(s * cli.TTS_SR), np.float32) for s in seconds]


def test_an_action_is_a_beat_of_its_own_between_two_sentences():
    sc = {"id": "s1", "chunks": ["a", "b"], "who": {1: "Spotter"},
          "acts": {0: [("Spotter", "jump", "motion", 1.1)], 1: [("Spotter", "wave", "clip", 0.5)], 2: [("Spotter", "wink", "clip", 0.7)]}}
    acts = []; ev, clips, total = cli.build_timeline([sc], [audio(1.0, 0.5)], [{"0": 0, "1": 0}], acts_out=acts, present={0: {"Spotter"}})
    P, G, A = cli.PRE_ROLL, cli.CHUNK_GAP, cli.ACT_GAP
    assert ev[0] == (pytest.approx(P), 0, -1)                                                                  # the slide opens with the character, for its first action
    assert ev[1] == (pytest.approx(P + 1.1 + A), 0, 0)                                                         # then the first sentence, after the jump
    assert [(round(s, 2), round(e, 2), n, k) for s, e, n, k, kind in acts] == [
        (round(P, 2), round(P + 1.1, 2), "Spotter", "jump"), (round(P + 1.1 + A + 1.0 + G, 2), round(P + 1.1 + A + 1.0 + G + 0.5, 2), "Spotter", "wave"),
        (round(acts[1][1] + A + 0.5 + G, 2), round(acts[1][1] + A + 0.5 + G + 0.7, 2), "Spotter", "wink")]
    assert [c[3] for c in clips] == ["", "Spotter"] and clips[0][0] == pytest.approx(P + 1.1 + A)
    plain = cli.build_timeline([{"id": "s1", "chunks": ["a", "b"]}], [audio(1.0, 0.5)], [{"0": 0, "1": 0}])
    assert total == pytest.approx(plain[2] + (1.1 + A) + (0.5 + A) + (0.7 + A))                               # three beats, and nothing else changes


def test_an_action_of_a_character_that_is_not_on_the_slide_does_nothing():
    sc = {"id": "s1", "chunks": ["a"], "acts": {0: [("Spotter", "jump", "motion", 1.1)]}}
    plain = cli.build_timeline([{"id": "s1", "chunks": ["a"]}], [audio(1.0)], [{"0": 0}])
    gone = cli.build_timeline([sc], [audio(1.0)], [{"0": 0}], present={0: set()})
    assert gone[0] == plain[0] and gone[2] == plain[2]
    here = cli.build_timeline([sc], [audio(1.0)], [{"0": 0}], present={0: {"Spotter"}})
    assert here[2] > plain[2] + 1.0


def test_a_timeline_without_characters_is_what_it_always_was():
    scenes = [{"id": "s1", "chunks": ["a", "b"]}, {"id": "s2", "chunks": ["c"], "hold": 2.0}]
    ev, clips, total = cli.build_timeline(scenes, [audio(1.0, 0.5), audio(0.8)], [{"0": 0.2, "1": 0.9}, {"0": 0}], hold=0.5)
    P, G, S = cli.PRE_ROLL, cli.CHUNK_GAP, cli.SCENE_GAP
    assert [e[1:] for e in ev] == [(0, 0), (0, 1), (1, 0)] and ev[0][0] == pytest.approx(P) and ev[1][0] == pytest.approx(P + 1.0 + G)
    t1 = max(P + 1.0 + G + 0.5 + G, P + 1.0 + G + 0.9 + cli.SETTLE_HOLD) + 0.5                                  # the slide's last graphic, then the pacing hold
    assert ev[2][0] == pytest.approx(t1 + S) and len(clips[0]) == 4
    assert total == pytest.approx(10.15)                       # 0.6 + two sentences + a slide change + the last slide's own 2 s hold + the ending, worked out by hand


# ---------------------------------------------------------------- the player

def player(tmp_path, text, setup=""):
    m, p = page(text); f = tmp_path / "m.html"; f.write_text(p); return f


def test_the_player_performs_an_action_before_the_sentence_it_belongs_to(tmp_path):
    actor("wave")
    f = player(tmp_path, "Title: T\nVoice: Spotter = Puppy\n## A\nSpotter animate: jump\nSay: First sentence.\nSpotter animate: wave\nSay: Second sentence here.\n")
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(); pg.goto(f.as_uri())
        pg.evaluate("""() => { window.__log = []; const T = () => Math.round(performance.now());
            addEventListener('message', e => { if (e.data && e.data.html2mp4 === 'step') __log.push(['step' + e.data.pos, T()]); });
            const st = document.getElementById('stage'); let seen = {};
            new MutationObserver(() => {
              const sp = st.querySelector('.h2m-sprite'), ac = st.querySelector('.h2m-actor');
              if (st.querySelector('#s1.active') && !seen.open) { seen.open = 1; __log.push(['open', T()]); }
              if (sp && sp.style.transform && !seen.jump) { seen.jump = 1; __log.push(['jump', T()]); }
              if (ac && ac.classList.contains('acting') && !seen.wave) { seen.wave = 1; __log.push(['wave', T()]); }
            }).observe(st, {subtree: true, attributes: true, attributeFilter: ['class', 'style']}); }""")
        pg.click("#play"); pg.wait_for_function("window.__log.some(x => x[0] === 'step1')", timeout=40000)
        order = [x[0] for x in pg.evaluate("window.__log")]; b.close()
    assert order.index("open") < order.index("jump") < order.index("step0") < order.index("wave") < order.index("step1")      # open, jump, sentence, wave, sentence


def test_pausing_stops_an_action_and_leaves_the_slide_clean(tmp_path):
    actor("wave")
    f = player(tmp_path, "Title: T\nVoice: Spotter = Puppy\n## A\nSay: One.\nSpotter animate: wave\nSay: Two.\nSpotter animate: jump\nSay: Three.\n")
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(); pg.goto(f.as_uri())
        pg.click("#play"); pg.wait_for_function("document.querySelector('.h2m-actor.acting')", timeout=40000)
        pg.click("#play")                                                                                         # pause in the middle of the wave
        left = pg.evaluate("""() => ({acting: document.querySelectorAll('.h2m-actor.acting').length, on: document.querySelectorAll('video.h2m-act.on').length,
                                       moved: [...document.querySelectorAll('.h2m-sprite')].filter(e => e.style.transform).length})""")
        b.close()
    assert left == {"acting": 0, "on": 0, "moved": 0}


def test_an_action_of_a_character_that_is_not_on_the_slide_is_skipped_by_the_player(tmp_path):
    actor("wave")
    m = script.parse("Title: T\nVoice: Spotter = Puppy\n## A\nSay: One.\nSpotter animate: jump\nSay: Two.\n")
    f = tmp_path / "m.html"; f.write_text(compose.assemble(m, config.brand(), [("custom", '<h2 class="t-heading" data-c="0">No dog here</h2>')], "", motion="calm"))
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(); pg.goto(f.as_uri())
        pg.evaluate("""() => { window.__steps = []; addEventListener('message', e => { if (e.data && e.data.html2mp4 === 'step') __steps.push([e.data.pos, performance.now()]); }); }""")
        pg.click("#play"); pg.wait_for_function("window.__steps.length >= 2", timeout=40000); s = pg.evaluate("window.__steps"); b.close()
    assert s[1][1] - s[0][1] < 6000                                                                               # the jump did not add its second to the wait


# ---------------------------------------------------------------- the renderer

def test_the_renderer_opens_a_slide_with_its_character_and_steps_an_action_exactly(tmp_path):
    actor("wave")
    f = player(tmp_path, "Title: T\nVoice: Spotter = Puppy\n## A\nSpotter animate: jump\nSay: First sentence.\nSpotter animate: wave\nSay: Second one.\n")
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1280, "height": 720}); pg.goto(f.as_uri()); pg.add_style_tag(content=cli.PAGE_CSS)
        pg.evaluate(cli.PAGE_JS, ["s1"]); pg.evaluate("__html2mp4.reset()")
        assert pg.evaluate("__html2mp4.actors()") == [["Spotter"]]
        pg.evaluate("__html2mp4.show(0, -1, 1.0)")                                                                # the slide opens for the first action
        opened = pg.evaluate("""() => ({active: document.getElementById('s1').classList.contains('active'),
              heading: document.querySelector('#s1 h2').classList.contains('on'), dog: document.querySelector('#s1 .h2m-actor').closest('[data-c]').classList.contains('on')})""")
        assert opened == {"active": True, "heading": False, "dog": True}                                          # the dog is there; the slide's own content waits for its sentence
        pg.evaluate("__html2mp4.frame(1.55, null, ['Spotter', 'jump', 'motion', 0.55, 1.1])")
        norm = "(s => { const e = document.createElement('div'); e.style.transform = s; return e.style.transform; })"      # the browser's own spelling of a transform
        sprite = pg.evaluate("document.querySelector('#s1 .h2m-sprite').style.transform"); want = pg.evaluate(f"{norm}(h2mMotion('jump', 0.5))")
        assert sprite == want and "translate(0%, -" in sprite and want != pg.evaluate(f"{norm}(h2mMotion('jump', 0))")
        pg.evaluate("__html2mp4.frame(3.0, null, ['Spotter', 'wave', 'clip', 0.25, 0.5])")
        clip_state = pg.evaluate("""() => { const v = document.querySelector('#s1 video[data-act=wave]'); return {acting: document.querySelector('#s1 .h2m-actor').classList.contains('acting'),
              on: v.classList.contains('on'), t: Math.round(v.currentTime * 100) / 100, sprite: document.querySelector('#s1 .h2m-sprite').style.transform}; }""")
        assert clip_state["acting"] and clip_state["on"] and abs(clip_state["t"] - 0.25) < 0.09 and clip_state["sprite"] == ""
        pg.evaluate("__html2mp4.frame(4.0, 'Spotter', null)")
        done = pg.evaluate("""() => ({acting: document.querySelectorAll('.h2m-actor.acting').length, on: document.querySelectorAll('video.h2m-act.on').length,
              moved: [...document.querySelectorAll('.h2m-sprite')].filter(e => e.style.transform).length, speaker: document.getElementById('stage').getAttribute('data-speaker')})""")
        b.close()
    assert done == {"acting": 0, "on": 0, "moved": 0, "speaker": "Spotter"}


def test_the_picture_of_a_character_is_really_drawn(tmp_path):
    actor("wave")                                                                                                  # (a custom property would silently drop a picture this large)
    f = player(tmp_path, "Title: T\nVoice: Spotter = Puppy\n## A\nSay: One.\nSpotter animate: wave\n")
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1280, "height": 720}); pg.goto(f.as_uri()); pg.add_style_tag(content=cli.PAGE_CSS)
        pg.evaluate(cli.PAGE_JS, ["s1"]); pg.evaluate("__html2mp4.reset()"); pg.evaluate("__html2mp4.show(0, 0, 1.0)"); pg.evaluate("__html2mp4.frame(1.2, null, null)")
        got = pg.evaluate("""() => { const s = document.querySelector('#s1 .h2m-sprite'), r = s.getBoundingClientRect(); return {bg: getComputedStyle(s).backgroundImage.slice(0, 22), w: s.offsetWidth, h: s.offsetHeight}; }""")
        b.close()
    assert got["bg"].startswith('url("data:image/webp') and got["w"] == 300 and got["h"] > 300


# ---------------------------------------------------------------- the designer and the checks

def test_the_designer_is_told_who_speaks_who_is_printed_and_what_happens():
    actor("wave")
    m = script.parse("Title: T\nVoice: Spotter = Puppy\n## A\nSay: One.\nSpotter animate: wave\nSpotter say: Two spoken words.\nSpotter bubble: Three printed words.\n")
    text = design._scenes_text(m, ["s1"])
    assert "Character on this slide: Spotter (image ID `spotter`" in text and "voice only, never write these words" in text and "PRINTED" in text
    assert "before step 1: Spotter wave" in text


def test_spoken_lines_must_not_be_printed_and_printed_lines_must():
    actor("wave")
    m = script.parse("Title: T\nVoice: Spotter = Puppy\n## A\nSay: One.\nSpotter say: Two spoken words here.\nSpotter bubble: Three printed words here.\nSpotter animate: moonwalk\n")
    def issues(inner): return [(i.severity, i.message) for i in design._character_issues(m, {"s1": {"html": inner, "css": "", "layout": "x"}})]
    ok = '<div data-c="0"><img data-asset="spotter" alt="Spotter"></div><p data-c="2">Three printed words here.</p>'
    got = issues(ok); assert len(got) == 1 and got[0][0] == "warn" and "moonwalk" in got[0][1] and "can:" in got[0][1]            # only the animation he can't do
    printed = issues(ok + "<p>Two spoken words here.</p>"); assert any(s == "error" and "spoken only" in msg for s, msg in printed)
    missing = issues(ok.replace("<p data-c=\"2\">Three printed words here.</p>", "")); assert any(s == "error" and "marked to be printed" in msg for s, msg in missing)
    absent = issues("<p data-c=\"2\">Three printed words here.</p>"); assert any(s == "error" and "isn't on the slide" in msg for s, msg in absent)
    assert not any("spoken only" in msg for _, msg in issues(ok + "<p>Two spoken</p>"))                                             # a couple of the same words isn't printing a line
    media.delete("spotter"); assert any(s == "warn" and "no character in the media library" in msg for s, msg in issues(ok))


def test_the_assistant_knows_the_character_words():
    from html2mp4 import chat
    for word in ("`NAME say:", "`NAME bubble:", "`NAME animate:", "Nothing is printed", "Puppy"): assert word in chat.SYSTEM
    assert "voice only" in design.SYSTEM and "PRINTED" in design.SYSTEM and "must NOT appear" in design.SYSTEM


# ---------------------------------------------------------------- the Studio

def test_the_studio_chooses_voices_and_actions_for_a_character(client, monkeypatch, tmp_path):
    monkeypatch.setattr("html2mp4.studio.PREVIEWS", tmp_path / "previews")                                     # not the samples already made for real
    ch = sprite(voice=""); c = clip("Wink clip", 0.7)
    v = client.get("/api/voices/characters").json()
    assert [x["id"] for x in v["voices"]][:2] == ["puppy", "pup-high"] and v["default"] == "am_puck|6|1.1"
    r = client.patch(f"/api/media/{ch['id']}", json={"voice": "Pup High"}).json()
    assert r["voice"] == "Pup High" and r["actor"]["motions"] == list(media.MOTIONS) and r["actor"]["clips"] == {}
    assert client.patch(f"/api/media/{ch['id']}", json={"voice": "Gandalf"}).status_code == 400
    r = client.post(f"/api/media/{ch['id']}/actions", json={"name": "wink", "clip": c["id"]}).json()
    assert r["actor"]["clips"]["wink"]["seconds"] == c["seconds"]
    assert client.post(f"/api/media/{ch['id']}/actions", json={"name": "x", "clip": ch["id"]}).status_code == 400
    assert client.delete(f"/api/media/{ch['id']}/actions/wink").json()["actor"]["clips"] == {}
    seen = []
    monkeypatch.setattr(cli, "synthesize", lambda scenes, voice, speed, cache, *a, **k: (seen.append((voice, scenes[0]["chunks"][0])), [[np.zeros(2400, np.float32)]])[1])
    monkeypatch.setattr("html2mp4.studio.to_m4a", lambda src, dst, **k: dst.write_bytes(b"audio"))
    assert client.get("/api/voice-sample/puppy").status_code == 200 and seen[0][0] == "am_puck|6|1.1" and "Spotter" in seen[0][1]
    assert client.get("/api/voice-sample/af_heart").status_code == 200 and "narrating" in seen[1][1]               # narrators are sampled as before
    assert client.get("/api/voice-sample/gandalf").status_code == 404
    assert {i["id"]: i["video"] for i in client.get("/api/media").json()["items"]}[c["id"]] is True


def test_a_character_without_a_voice_line_speaks_in_its_library_voice_or_the_default():
    ch = sprite(voice="Pup High")
    m = script.parse("Title: T\n## A\nSay: One.\nSpotter say: Two.\n")
    assert m.voices == {"Spotter": None}
    assert compose.scenes_js(m).startswith('var voices = {"Spotter": "am_puck|8|1.12"};')                                # the library's choice
    media.update(ch["id"], voice="")
    assert compose.scenes_js(m).startswith('var voices = {"Spotter": "am_puck|6|1.1"};')                                # then the default (Puppy)
    other = script.parse("Title: T\n## A\nSay: One.\nZelda say: Two.\n")
    assert compose.scenes_js(other).startswith('var voices = {"Zelda": "am_puck|6|1.1"};')                              # no such character in the library either
    named = script.parse("Title: T\nVoice: Spotter = Heart\n## A\nSay: One.\nSpotter say: Two.\n")
    assert compose.scenes_js(named).startswith('var voices = {"Spotter": "af_heart"};')                                 # the script wins


def test_a_module_with_character_clips_still_reads_well_as_yaml_and_still_carries_them(client):
    from html2mp4 import projects
    actor("wave")
    text = "Title: T\nVoice: Spotter = Puppy\n## A\nSay: One.\nSpotter animate: wave\nSay: Two.\n"
    p = projects.create("T", text); m, html = page(text)
    projects.save_version(p["id"], html, None, "Quick layout")
    view = client.get(f"/api/projects/{p['id']}/export", params={"format": "yaml", "inline": "true"}).text
    assert "<embedded video, " in view and "<embedded image, " in view and "data:video" not in view and "base64," not in view      # a line each, not pages of encoded data
    assert "data:video/webm;base64," in client.get(f"/api/projects/{p['id']}/export").text                                         # the file itself keeps them


def test_a_jump_is_really_drawn_even_when_the_designer_puts_the_reveal_on_the_picture_itself(tmp_path):
    actor()                                                                                                        # no clips: only the built-in motions
    m = script.parse("Title: T\nVoice: Spotter = Puppy\n## A\nSay: One.\nSpotter animate: jump\n")
    inner = '<h2 data-c="0">Hi</h2><img data-asset="spotter" alt="Spotter" data-c="0" data-fx="rise" style="width:260px;position:absolute;right:60px;bottom:40px">'
    f = tmp_path / "m.html"; f.write_text(compose.assemble(m, config.brand(), [("custom", inner)], "", motion="calm"))
    assert 'class="h2m-actor' in f.read_text() and 'data-c="0"' in re.search(r'<span role="img"[^>]*class="h2m-actor[^>]*>', f.read_text()).group(0)       # the reveal sits on the box
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1280, "height": 720}); pg.goto(f.as_uri()); pg.add_style_tag(content=cli.PAGE_CSS)
        pg.evaluate(cli.PAGE_JS, ["s1"]); pg.evaluate("__html2mp4.reset()"); pg.evaluate("__html2mp4.show(0, 0, 1.0)")
        top = lambda act: (pg.evaluate(f"__html2mp4.frame(5.0, null, {json.dumps(act)})"), pg.wait_for_timeout(60),
                           pg.evaluate("document.querySelector('.h2m-sprite').getBoundingClientRect().y"))[2]
        rest = top(None); peak = top(["Spotter", "jump", "motion", 0.55, 1.1]); again = top(None)
        b.close()
    assert rest - peak > 40 and abs(again - rest) < 2                                                              # he is clearly higher at the top of the jump, and back down after


# ---------------------------------------------------------------- sharing a character as one file

def _zip(files, manifest=None):
    import io, zipfile
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        if manifest is not None: z.writestr("character.json", json.dumps(manifest) if not isinstance(manifest, (bytes, str)) else manifest)
        for k, v in files.items(): z.writestr(k, v)
    return b.getvalue()


def _entry(**kw): return {"id": "x", "name": "X", "kind": "mascot", "file": "x.webp", "format": "webp", "w": 4, "h": 4, "transparent": True, "animated": {"frames": 1, "fps": 12, "mode": "character", "rows": 1}, **kw}


def test_a_character_travels_as_one_file_and_comes_back_whole(tmp_path, monkeypatch):
    import io, zipfile
    ch = actor("wave", "wink"); cut = clip("Cut out", 0.5)
    items = media.listing(); next(i for i in items if i["id"] == ch["id"]).update(parent=cut["id"], speaker="Spotter", voice="Pup High"); media._save(items)
    name, data = media.export_bundle(ch["id"])
    z = zipfile.ZipFile(io.BytesIO(data)); manifest = json.loads(z.read("character.json"))
    assert name == "spotter.h2m-character.zip" and manifest["format"] == media.BUNDLE_FORMAT and manifest["main"] == ch["id"]
    assert len(manifest["items"]) == 4 and "README.txt" in z.namelist() and len(data) < 1_000_000                       # the character, two clips and the cut-out
    monkeypatch.setattr(media, "MEDIA", tmp_path / "another-computer")                                                  # her library: empty
    it, notes = media.import_bundle(data)
    assert it["name"] == "Spotter" and notes == [] and it["speaker"] == "Spotter" and it["voice"] == "Pup High" and it["animated"]["rows"] == 2
    assert set(it["actions"]) == {"wave", "wink"} and all(media.get(c)["format"] == "webm" and media.path(media.get(c)).exists() for c in it["actions"].values())
    assert media.get(it["parent"])["name"] == "Cut out" and media.image(it, 3, 1).size == (60, 80) and media.actions_of(it)["wink"] == media.get(it["actions"]["wink"])["seconds"]
    m = script.parse("Title: T\n## A\nSay: One.\nSpotter animate: wink\nSay: Two.\n")                                        # and a script uses him straight away
    assert media.cast_for(m)["by_slide"] == {"s1": {"Spotter": {"wink"}}} and media.actor_voice("Spotter") == "Pup High"
    again, notes2 = media.import_bundle(data)                                                                          # importing twice never overwrites
    assert again["id"] != it["id"] and again["name"] == "Spotter (2)" and notes2 and "already a character" in notes2[0]
    assert set(again["actions"].values()).isdisjoint(it["actions"].values()) and set(again["actions"]) == {"wave", "wink"}
    assert len(media.listing()) == 8


def test_only_a_talking_character_can_be_exported_and_only_a_real_character_file_imported(tmp_path):
    still = media.add(_png(), "Still.png")
    with pytest.raises(media.MediaError, match="Only a talking character"): media.export_bundle(still["id"])
    png = _png(); ok = {"x.webp": png}
    bad = {
        "not a zip": b"hello",
        "no manifest": _zip({"x.webp": png}),
        "unreadable manifest": _zip({"x.webp": png}, "{not json"),
        "wrong format": _zip(ok, {"format": "something.else", "schema": 1, "main": "x", "items": [_entry()]}),
        "no main item": _zip(ok, {"format": media.BUNDLE_FORMAT, "schema": 1, "main": "nope", "items": [_entry()]}),
        "path out of the library": _zip({"x.webp": png}, {"format": media.BUNDLE_FORMAT, "schema": 1, "main": "x", "items": [_entry(file="../x.webp")]}),
        "a file that isn't in the zip": _zip({}, {"format": media.BUNDLE_FORMAT, "schema": 1, "main": "x", "items": [_entry()]}),
        "a script": _zip({"x.py": b"print(1)"}, {"format": media.BUNDLE_FORMAT, "schema": 1, "main": "x", "items": [_entry(file="x.py")]}),
        "an image that isn't one": _zip({"x.webp": b"not an image"}, {"format": media.BUNDLE_FORMAT, "schema": 1, "main": "x", "items": [_entry()]}),
        "a video that isn't one": _zip({"x.webm": b"not a video"}, {"format": media.BUNDLE_FORMAT, "schema": 1, "main": "x", "items": [_entry(file="x.webm", format="webm")]}),
    }
    for what, data in bad.items():
        with pytest.raises(media.MediaError): media.import_bundle(data)
    with pytest.raises(media.MediaError, match="newer Studio"): media.import_bundle(_zip(ok, {"format": media.BUNDLE_FORMAT, "schema": 99, "main": "x", "items": [_entry()]}))
    with pytest.raises(media.MediaError, match="too large"): media.import_bundle(_zip({f"f{i}.webp": png for i in range(media.BUNDLE_MAX_FILES + 1)}, {"format": media.BUNDLE_FORMAT, "schema": 1, "main": "x", "items": [_entry()]}))
    assert [i["id"] for i in media.listing()] == [still["id"]]                                                          # nothing half-imported
    it, _ = media.import_bundle(_zip(ok, {"format": media.BUNDLE_FORMAT, "schema": 1, "main": "x", "items": [_entry(speaker="Zed", evil="x" * 9, kind="wizard", description="d" * 900)]}))
    assert it["name"] == "X" and it["kind"] == "other" and len(it["description"]) == 400 and "evil" not in it                # only known fields, tidied


def test_the_studio_exports_and_imports_a_character(client, tmp_path, monkeypatch):
    ch = actor("wave")
    r = client.get(f"/api/media/{ch['id']}/bundle")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip" and "spotter.h2m-character.zip" in r.headers["content-disposition"]
    assert client.get(f"/api/media/{media.add(_png(), 'Still.png')['id']}/bundle").status_code == 400
    monkeypatch.setattr(media, "MEDIA", tmp_path / "other")
    got = client.post("/api/media/import", files={"file": ("Spotter.h2m-character.zip", r.content, "application/zip")}).json()
    assert got["item"]["name"] == "Spotter" and got["item"]["actor"]["clips"]["wave"]["seconds"] == 0.5 and got["notes"] == []
    bad = client.post("/api/media/import", files={"file": ("x.zip", b"nope", "application/zip")})
    assert bad.status_code == 422 and "isn't a character file" in bad.json()["detail"]
