import json
import os
import re

import logging

import anthropic

MODEL = "claude-haiku-5-5"
log = logging.getLogger("bedtime_story")


def make_client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key)


def get_client() -> anthropic.Anthropic:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("Set the ANTHROPIC_API_KEY environment variable before running.")
    return make_client(api_key)


def call_model(client, system: str, prompt: str, max_tokens: int = 4000) -> str:
    resp = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
    if not text.strip():
        block_types = [getattr(block, "type", "?") for block in resp.content]
        log.warning("model returned no text; stop_reason=%s block_types=%s", getattr(resp, "stop_reason", None), block_types)
        raise ValueError("The model returned no text.")
    return text


def parse_json(text: str) -> dict:
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        if start == -1:
            raise ValueError("No JSON object found in model output.")
        try:
            value, _ = json.JSONDecoder().raw_decode(cleaned[start:])
        except json.JSONDecodeError as exc:
            raise ValueError(f"Model output was not valid JSON: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError("Model output was JSON but not an object.")
    return value
