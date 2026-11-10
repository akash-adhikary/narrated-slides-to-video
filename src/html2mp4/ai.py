"""Calls to Claude, in one place: credentials, the model, refusal fallback, structured output and plain errors."""
import json

import anthropic

from html2mp4 import config

FALLBACK_BETA = "server-side-fallback-2026-07-01"     # with fallbacks="default": a declined request is retried server-side


class AIError(Exception):
    """A Claude call failed; the message is written for the person using the Studio."""


def available():
    return config.api_key_status()["set"]


def client(timeout=600):
    key = config.api_key()
    try:
        return anthropic.Anthropic(api_key=key, timeout=timeout, max_retries=2) if key else anthropic.Anthropic(timeout=timeout, max_retries=2)
    except anthropic.AnthropicError:
        raise AIError("No Anthropic API key is set. Add one in Settings.")


def structured(system, content, schema, effort="medium", max_tokens=32000, on_text=None, on_thinking=None):
    """One request whose answer must match `schema`. Returns (data, usage).

    `on_text(text_so_far)` is called as the answer streams in, and `on_thinking(summary_so_far)` as Claude's thinking summary does
    (the summary is what Anthropic exposes of its reasoning; it is billed the same whether or not it is shown)."""
    c = client()
    try:
        with c.beta.messages.stream(
            model=config.DESIGN_MODEL, max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}] if isinstance(system, str) else system,
            messages=[{"role": "user", "content": content}],
            thinking={"type": "adaptive", "display": "summarized" if on_thinking else "omitted"},
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            betas=[FALLBACK_BETA], fallbacks="default",
        ) as stream:
            so_far = ""
            for event in stream:
                if event.type == "text" and on_text:
                    so_far += event.text; on_text(so_far)
                elif event.type == "thinking" and on_thinking:
                    on_thinking(event.snapshot)
            msg = stream.get_final_message()
    except TypeError:          # the SDK found no credentials anywhere
        raise AIError("No Anthropic API key is set. Add one in Settings.")
    except anthropic.AuthenticationError:
        raise AIError("Anthropic didn't accept the API key. Check it in Settings.")
    except anthropic.PermissionDeniedError:
        raise AIError("The API key doesn't have access to the model used for designing slides.")
    except anthropic.RateLimitError:
        raise AIError("Anthropic's rate limit was reached. Wait a minute and try again.")
    except anthropic.APIConnectionError:
        raise AIError("Couldn't reach Anthropic. Check your internet connection.")
    except anthropic.APIStatusError as e:
        raise AIError(f"Anthropic returned an error ({e.status_code}). Try again in a moment.")
    if msg.stop_reason == "refusal":
        raise AIError("Claude declined this request. Try rewording the script.")
    if msg.stop_reason == "max_tokens":
        raise AIError("Claude's answer was cut off because it was too long. Try a shorter script.")
    text = "".join(b.text for b in msg.content if b.type == "text")
    try:
        return json.loads(text), msg.usage
    except ValueError:
        raise AIError("Claude's answer wasn't in the expected format. Try again.")


def cost(usage):
    """Approximate US$ for one call at Claude Opus 5.5 list prices ($4 in / $20 out per million tokens; cache reads $0.20)."""
    return (usage.input_tokens * 4 + (getattr(usage, "cache_creation_input_tokens", 0) or 0) * 5
            + (getattr(usage, "cache_read_input_tokens", 0) or 0) * 0.2 + usage.output_tokens * 20) / 1e6
