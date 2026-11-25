from judge import judge_story
from llm import call_model, parse_json
from prompts import (
    ANALYZER_PROMPT,
    ANALYZER_SYSTEM,
    CATEGORIES,
    REVISER_PROMPT,
    STORY_BRIEF,
    STORYTELLER_SYSTEM,
    USER_FEEDBACK_PROMPT,
)

MAX_REVISION_ROUNDS = 2
DEFAULT_BRIEF = {
    "category": "general",
    "characters": [],
    "setting": "anywhere the story needs",
    "tone": "gentle",
    "target_words": 350,
}


def analyze_request(client, request: str) -> dict:
    prompt = ANALYZER_PROMPT.format(request=request, categories=", ".join(CATEGORIES))
    try:
        brief = parse_json(call_model(client, ANALYZER_SYSTEM, prompt, max_tokens=2000))
    except (ValueError, TypeError):
        return dict(DEFAULT_BRIEF)
    brief = {**DEFAULT_BRIEF, **brief}
    if brief["category"] not in CATEGORIES:
        brief["category"] = "general"
    brief["target_words"] = min(max(int(brief["target_words"]), 250), 500)
    return brief


def _storyteller_system(brief: dict) -> str:
    return STORYTELLER_SYSTEM.format(category_guidance=CATEGORIES[brief["category"]])


def _brief_text(request: str, brief: dict) -> str:
    return STORY_BRIEF.format(
        request=request,
        characters=", ".join(brief["characters"]) or "as the request implies",
        setting=brief["setting"],
        tone=brief["tone"],
        target_words=brief["target_words"],
    )


def write_first_draft(client, request: str, brief: dict) -> str:
    return call_model(
        client,
        system=_storyteller_system(brief),
        prompt=_brief_text(request, brief),
        max_tokens=6000,
    )


def revise(client, request: str, brief: dict, story: str, feedback: list[str]) -> str:
    return call_model(
        client,
        system=_storyteller_system(brief),
        prompt=REVISER_PROMPT.format(
            request=request,
            characters=", ".join(brief["characters"]) or "as the request implies",
            setting=brief["setting"],
            tone=brief["tone"],
            story=story,
            feedback="\n".join(f"- {item}" for item in feedback),
        ),
        max_tokens=6000,
    )


def improve_story(client, request: str, brief: dict, story: str) -> dict:
    history = []
    review = judge_story(client, request, story)
    history.append({"story": story, **review})
    rounds = 0
    while not review["passed"] and rounds < MAX_REVISION_ROUNDS:
        story = revise(client, request, brief, story, review["feedback"])
        review = judge_story(client, request, story)
        history.append({"story": story, **review})
        rounds += 1
    return {"story": story, "history": history}


def generate_story(client, request: str) -> dict:
    brief = analyze_request(client, request)
    draft = write_first_draft(client, request, brief)
    result = improve_story(client, request, brief, draft)
    return {"request": request, "brief": brief, **result}


def apply_user_feedback(client, state: dict, user_feedback: str) -> dict:
    story = call_model(
        client,
        system=_storyteller_system(state["brief"]),
        prompt=USER_FEEDBACK_PROMPT.format(
            request=state["request"], story=state["story"], user_feedback=user_feedback
        ),
        max_tokens=6000,
    )
    result = improve_story(client, state["request"], state["brief"], story)
    return {**state, **result}
