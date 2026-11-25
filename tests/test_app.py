import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as web
import keystore

FAKE_KEY = "sk-ant-api03-TESTKEYTESTKEYTESTKEY1234"
HEADERS = {"X-Story-Client": "1"}
GOOD = {"age_fit": 5, "request_fidelity": 5, "story_arc": 5, "engagement": 5, "bedtime_calm": 5, "safety": 5}


class Block:
    type = "text"

    def __init__(self, text):
        self.text = text


class Response:
    def __init__(self, text):
        self.content = [Block(text)]


class FakeMessages:
    def create(self, **kwargs):
        system = kwargs["system"]
        if "classify" in system:
            return Response(json.dumps({"category": "animal_friends", "characters": ["Alice"],
                                        "setting": "garden", "tone": "gentle", "target_words": 300}))
        if "strict editor" in system:
            return Response(json.dumps({"scores": GOOD, "feedback": []}))
        return Response("The Sleepy Garden\n\nAlice and her cat sat in the garden. They watched the stars.")


class FakeClient:
    messages = FakeMessages()


class AppTests(unittest.TestCase):
    def setUp(self):
        web.app.config["TESTING"] = True
        self.client = web.app.test_client()
        keystore.clear_key()
        web.runs.clear()
        web.recent_calls.clear()
        import sample_log, tempfile
        self._log_dir = tempfile.mkdtemp()
        self._log_patch = mock.patch.object(sample_log, "LOG_PATH", Path(self._log_dir) / "samples.md")
        self._log_patch.start()

    def tearDown(self):
        keystore.clear_key()
        self._log_patch.stop()

    def post_json(self, path, body, headers=HEADERS, host="127.0.0.1:5000"):
        return self.client.post(path, data=json.dumps(body), headers={**headers, "Content-Type": "application/json"},
                                base_url=f"http://{host}")

    def test_index_has_security_headers(self):
        resp = self.client.get("/", base_url="http://127.0.0.1:5000")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("default-src 'self'", resp.headers["Content-Security-Policy"])
        self.assertNotIn("unsafe-inline", resp.headers["Content-Security-Policy"])
        self.assertEqual(resp.headers["X-Frame-Options"], "DENY")

    def test_rejects_foreign_host_header(self):
        resp = self.client.get("/", base_url="http://evil.example.com")
        self.assertEqual(resp.status_code, 400)

    def test_rejects_foreign_origin(self):
        resp = self.post_json("/api/key", {"key": FAKE_KEY}, headers={**HEADERS, "Origin": "http://evil.example.com"})
        self.assertEqual(resp.status_code, 403)

    def test_rejects_missing_custom_header(self):
        resp = self.post_json("/api/key", {"key": FAKE_KEY}, headers={})
        self.assertEqual(resp.status_code, 403)

    def test_rejects_invalid_key_format(self):
        resp = self.post_json("/api/key", {"key": "not-a-key"})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(keystore.status()["set"])

    def test_key_is_stored_masked_and_never_echoed(self):
        resp = self.post_json("/api/key", {"key": FAKE_KEY})
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(FAKE_KEY, resp.get_data(as_text=True))
        self.assertEqual(resp.get_json()["hint"], FAKE_KEY[-4:])
        status = self.client.get("/api/key", base_url="http://127.0.0.1:5000").get_data(as_text=True)
        self.assertNotIn(FAKE_KEY, status)

    def test_forget_key_clears_it(self):
        self.post_json("/api/key", {"key": FAKE_KEY})
        resp = self.client.delete("/api/key", headers=HEADERS, base_url="http://127.0.0.1:5000")
        self.assertFalse(resp.get_json()["set"])

    def test_story_requires_key(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            resp = self.post_json("/api/runs", {"request": "A dragon"})
        self.assertEqual(resp.status_code, 401)

    def test_story_run_returns_trace_without_key(self):
        self.post_json("/api/key", {"key": FAKE_KEY})
        with mock.patch.object(web, "make_client", return_value=FakeClient()):
            resp = self.post_json("/api/runs", {"request": "Alice and her cat"})
        self.assertEqual(resp.status_code, 201)
        body = resp.get_data(as_text=True)
        self.assertNotIn(FAKE_KEY, body)
        data = resp.get_json()
        self.assertTrue(data["history"][0]["passed"])
        stages = [c["stage"] for c in data["trace"]]
        self.assertEqual(stages, ["Request analyzer", "First draft", "Judge"])

    def test_feedback_adds_to_same_run(self):
        self.post_json("/api/key", {"key": FAKE_KEY})
        with mock.patch.object(web, "make_client", return_value=FakeClient()):
            run = self.post_json("/api/runs", {"request": "Alice and her cat"}).get_json()
            resp = self.post_json(f"/api/runs/{run['id']}/feedback", {"change": "make it shorter"})
        self.assertEqual(resp.status_code, 200)
        stages = [c["stage"] for c in resp.get_json()["trace"]]
        self.assertIn("Reader feedback rewrite", stages)
        self.assertEqual(len(resp.get_json()["history"]), 1)

    def test_long_request_is_rejected(self):
        self.post_json("/api/key", {"key": FAKE_KEY})
        resp = self.post_json("/api/runs", {"request": "x" * 501})
        self.assertEqual(resp.status_code, 400)

    def test_prompts_endpoint_has_no_key(self):
        self.post_json("/api/key", {"key": FAKE_KEY})
        resp = self.client.get("/api/prompts", base_url="http://127.0.0.1:5000")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(FAKE_KEY, resp.get_data(as_text=True))
        self.assertGreaterEqual(len(resp.get_json()["prompts"]), 8)


if __name__ == "__main__":
    unittest.main()
