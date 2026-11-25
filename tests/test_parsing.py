import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from llm import parse_json
from judge import judge_story, JudgeFormatError


class Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class Response:
    def __init__(self, text):
        self.content = [Block(text)]


class ScriptedClient:
    def __init__(self, replies):
        self.replies = list(replies)
        self.messages = self

    def create(self, **kwargs):
        return Response(self.replies.pop(0))


GOOD_JSON = '{"scores": {"age_fit": 5, "request_fidelity": 5, "story_arc": 5, "engagement": 5, "bedtime_calm": 5, "safety": 5}, "feedback": []}'


class ParseTests(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(parse_json('{"a": 1}'), {"a": 1})

    def test_fenced_json(self):
        self.assertEqual(parse_json('```json\n{"a": 1}\n```'), {"a": 1})

    def test_trailing_text_after_object(self):
        self.assertEqual(parse_json('{"a": 1}\nHope this helps! {note}'), {"a": 1})

    def test_leading_prose(self):
        self.assertEqual(parse_json('Here is the review: {"a": 2}'), {"a": 2})

    def test_no_object_raises_value_error(self):
        with self.assertRaises(ValueError):
            parse_json("no json here")

    def test_broken_json_raises_value_error(self):
        with self.assertRaises(ValueError):
            parse_json('{"feedback": ["Use "simple" words."]}')


class JudgeRetryTests(unittest.TestCase):
    def test_retries_once_after_bad_reply(self):
        client = ScriptedClient(['{"feedback": ["Use "bad" quotes."]}', GOOD_JSON])
        review = judge_story(client, "x", "y")
        self.assertTrue(review["passed"])

    def test_two_bad_replies_raise_clear_error(self):
        client = ScriptedClient(["not json", "still not json"])
        with self.assertRaises(JudgeFormatError):
            judge_story(client, "x", "y")


if __name__ == "__main__":
    unittest.main()


class EmptyReplyTests(unittest.TestCase):
    def test_empty_reply_raises_value_error(self):
        from llm import call_model
        client = ScriptedClient(["", ""])
        with self.assertRaises(ValueError):
            call_model(client, "sys", "prompt")


class OutputBudgetTests(unittest.TestCase):
    def test_story_and_judge_budgets_leave_room_for_reasoning(self):
        import inspect
        import pipeline, judge
        src = inspect.getsource(pipeline) + inspect.getsource(judge)
        budgets = [int(n) for n in re.findall(r"max_tokens=(\d+)", src)]
        self.assertTrue(budgets)
        self.assertTrue(all(b >= 2000 for b in budgets), budgets)
