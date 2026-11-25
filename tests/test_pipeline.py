import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline import analyze_request, generate_story, MAX_REVISION_ROUNDS
from judge import judge_story


class Block:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class Response:
    def __init__(self, text):
        self.content = [Block(text)]


class FakeMessages:
    def __init__(self, owner):
        self.owner = owner

    def create(self, **kwargs):
        self.owner.calls.append(kwargs)
        system = kwargs["system"]
        if "classify" in system:
            return Response(json.dumps({
                "category": "animal_friends",
                "characters": ["Alice", "Bob the cat"],
                "setting": "a sunny garden",
                "tone": "silly",
                "target_words": 300,
            }))
        if "strict editor" in system:
            scores = self.owner.judge_scores.pop(0)
            feedback = [] if all(v >= 4 for v in scores.values()) else ["Shorten the long sentences."]
            return Response(json.dumps({"scores": scores, "feedback": feedback}))
        return Response("Alice and Bob the cat play in the garden. The end.")


class FakeClient:
    def __init__(self, judge_scores):
        self.judge_scores = list(judge_scores)
        self.calls = []
        self.messages = FakeMessages(self)


GOOD = {"age_fit": 5, "request_fidelity": 5, "story_arc": 5, "engagement": 5, "bedtime_calm": 5, "safety": 5}
WEAK = {"age_fit": 2, "request_fidelity": 5, "story_arc": 5, "engagement": 4, "bedtime_calm": 5, "safety": 5}


class PipelineTests(unittest.TestCase):
    def test_analyze_request_reads_brief(self):
        brief = analyze_request(FakeClient([]), "Alice and Bob the cat")
        self.assertEqual(brief["category"], "animal_friends")
        self.assertEqual(brief["target_words"], 300)

    def test_passing_draft_is_not_revised(self):
        client = FakeClient([GOOD])
        result = generate_story(client, "Alice and Bob the cat")
        self.assertEqual(len(result["history"]), 1)
        self.assertTrue(result["history"][0]["passed"])

    def test_failing_draft_is_revised_then_capped(self):
        client = FakeClient([WEAK] * (MAX_REVISION_ROUNDS + 1))
        result = generate_story(client, "Alice and Bob the cat")
        self.assertEqual(len(result["history"]), MAX_REVISION_ROUNDS + 1)
        self.assertFalse(result["history"][-1]["passed"])

    def test_judge_fills_missing_scores_with_one(self):
        class Minimal(FakeClient):
            def __init__(self):
                super().__init__([])
                self.messages = type("M", (), {"create": lambda s, **k: Response(json.dumps({"scores": {}, "feedback": []}))})()
        review = judge_story(Minimal(), "x", "y")
        self.assertFalse(review["passed"])
        self.assertTrue(all(v == 1 for v in review["scores"].values()))

    def test_bad_analyzer_output_falls_back_to_default(self):
        class Broken(FakeClient):
            def __init__(self):
                super().__init__([])
                self.messages = type("M", (), {"create": lambda s, **k: Response("not json")})()
        brief = analyze_request(Broken(), "anything")
        self.assertEqual(brief["category"], "general")


if __name__ == "__main__":
    unittest.main()
