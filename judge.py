import logging

from llm import call_model, parse_json
from prompts import JUDGE_PROMPT, JUDGE_SYSTEM

log = logging.getLogger("bedtime_story")

CRITERIA = ["age_fit", "request_fidelity", "story_arc", "engagement", "bedtime_calm", "safety"]
PASS_THRESHOLD = 4


class JudgeFormatError(ValueError):
    pass


def _ask_judge(client, request: str, story: str) -> dict:
    raw = call_model(
        client,
        system=JUDGE_SYSTEM,
        prompt=JUDGE_PROMPT.format(request=request, story=story),
        max_tokens=4000,
    )
    try:
        return parse_json(raw)
    except ValueError as exc:
        log.warning("judge reply could not be read: %s; starts with: %r", exc, raw[:200])
        raise


def judge_story(client, request: str, story: str) -> dict:
    try:
        result = _ask_judge(client, request, story)
    except ValueError:
        try:
            result = _ask_judge(client, request, story)
        except ValueError as exc:
            raise JudgeFormatError("The judge's reply could not be read after two attempts.") from exc
    scores = {c: int(result.get("scores", {}).get(c, 1)) for c in CRITERIA}
    feedback = [str(item) for item in result.get("feedback", [])][:4]
    passed = all(score >= PASS_THRESHOLD for score in scores.values())
    return {"scores": scores, "feedback": feedback, "passed": passed}
