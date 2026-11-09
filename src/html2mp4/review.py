"""Suggest fixes for a script before it's designed: typos, unclear lines, risky promises, hard-to-say words.

Suggestions are never applied automatically. Each one carries the exact quote from the script, so accepting it is a
plain text replacement, and a pronunciation suggestion goes to the glossary (it changes what is spoken, not the captions).
"""
from html2mp4 import ai

SCHEMA = {"type": "object", "properties": {"suggestions": {"type": "array", "items": {
    "type": "object", "properties": {
        "kind": {"type": "string", "enum": ["typo", "clarity", "risk", "pronounce"]},
        "quote": {"type": "string"}, "replacement": {"type": "string"}, "reason": {"type": "string"}},
    "required": ["kind", "quote", "replacement", "reason"], "additionalProperties": False}}},
    "required": ["suggestions"], "additionalProperties": False}

SYSTEM = """You are a careful editor for corporate training narration that will be read aloud by a text-to-speech voice.
Find only real problems; leave style and taste alone. Return at most 12 suggestions, most important first.

Kinds:
- typo: a spelling or grammar error or a garbled sentence. `replacement` is the corrected text.
- clarity: a line a new employee would not understand, or a sentence that contradicts itself. `replacement` is a clearer version
  that keeps the meaning.
- risk: wording that could read as a promise, guarantee or commitment (about promotion, pay, titles, outcomes, growth),
  or that could create a legal, HR or fairness concern. `replacement` is a safer version that keeps the meaning.
- pronounce: an abbreviation, acronym, symbol or unusual name a voice may say wrongly (for example "R&D", "DSA", "SQL").
  `quote` is the term exactly as written; `replacement` is how it should be SPOKEN (for example "R and D", "D S A").
  Only include terms that are actually likely to be mispronounced.

`quote` must be copied exactly from the script (a short phrase or one sentence), so it can be found and replaced.
Never rewrite for style. If the script is fine, return an empty list.

Ignore the script's structure: the first line (the title), "Scene N:" headings with their times, and the "On screen:",
"Show:", "Say:" and "Note:" labels are not narration. Review the narration and the on-screen text under them.
For `pronounce`, include only acronyms, abbreviations, symbols and unusual names. Ordinary words and well-known company or
product names are pronounced fine; leave them out."""


def review(script_text):
    """Returns ([suggestion dicts that really occur in the script], cost in dollars)."""
    data, usage = ai.structured(SYSTEM, f"Script:\n\n{script_text}", SCHEMA, effort="low", max_tokens=8000)
    found = [s for s in data["suggestions"] if s["quote"] and s["quote"] in script_text and s["replacement"] != s["quote"]]
    return found, ai.cost(usage)


def apply(script_text, suggestion):
    """Apply a typo, clarity or risk suggestion to the script text (first occurrence of the quote)."""
    return script_text.replace(suggestion["quote"], suggestion["replacement"], 1)
