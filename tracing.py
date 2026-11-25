from typing import List, Optional


def stage_label(system: str, prompt: str) -> str:
    if "classify" in system:
        return "Request analyzer"
    if "strict editor" in system:
        return "Judge"
    if "Requested change from the reader" in prompt:
        return "Reader feedback rewrite"
    if prompt.startswith("Rewrite the story below to address"):
        return "Reviser"
    return "First draft"


class _Messages:
    def __init__(self, owner: "TracingClient"):
        self.owner = owner

    def create(self, **kwargs):
        resp = self.owner._client.messages.create(**kwargs)
        output = "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")
        system, prompt = kwargs["system"], kwargs["messages"][0]["content"]
        self.owner.trace.append({
            "stage": stage_label(system, prompt),
            "model": kwargs["model"],
            "max_tokens": kwargs["max_tokens"],
            "system": system,
            "prompt": prompt,
            "output": output,
        })
        return resp


class TracingClient:
    """Wraps an Anthropic client and records each call. Never records the API key."""

    def __init__(self, client, trace: Optional[List[dict]] = None):
        self._client = client
        self.trace = trace if trace is not None else []
        self.messages = _Messages(self)
