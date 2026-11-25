"""
Bedtime story agent for children aged 5 to 10.

What I would build next with two more hours:
- An offline eval set of about 20 requests, scored automatically for age fit and length, to catch prompt regressions.
- A reading-level metric (Flesch-Kincaid) as a second judge signal, so scores are not based on the model's opinion alone.
- Saving a child's favorite characters and settings between sessions so later stories can call them back.
- Text-to-speech output so the story can be read aloud at bedtime.
"""

import anthropic

from llm import get_client
from pipeline import apply_user_feedback, generate_story

MAX_FEEDBACK_TURNS = 5


def show(state: dict) -> None:
    print("\n" + state["story"] + "\n")
    last = state["history"][-1]
    print(f"[judge scores: {last['scores']} | passed: {last['passed']}]\n")


def main() -> None:
    try:
        client = get_client()
    except RuntimeError as exc:
        print(exc)
        raise SystemExit(1)

    request = input("What kind of story do you want to hear? ").strip()
    if not request:
        print("Please describe a story to get started.")
        return

    try:
        state = generate_story(client, request)
        show(state)
        for _ in range(MAX_FEEDBACK_TURNS):
            change = input("Want any changes? (press Enter to finish) ").strip()
            if not change:
                break
            state = apply_user_feedback(client, state, change)
            show(state)
    except anthropic.AuthenticationError:
        print("Anthropic rejected this key. Check ANTHROPIC_API_KEY and try again.")
        raise SystemExit(1)
    except anthropic.APIError:
        print("The model request failed. Check your connection and account balance, then try again.")
        raise SystemExit(1)
    except ValueError as exc:
        print(f"The model's reply could not be used: {exc} Try again.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
