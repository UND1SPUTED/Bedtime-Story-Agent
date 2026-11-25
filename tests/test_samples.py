import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as web
import keystore
import sample_log
from test_app import FakeClient, FAKE_KEY

REAL_LOG = Path(__file__).resolve().parent.parent / "sample_outputs.md"
HEADERS = {"X-Story-Client": "1", "Content-Type": "application/json"}
SCORES = {"age_fit": 5, "request_fidelity": 4, "story_arc": 5, "engagement": 5, "bedtime_calm": 5, "safety": 5}


class SampleLogUnitTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = Path(self.dir) / "samples.md"
        self.path.write_text("# Existing notes\n\nKeep me.\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_append_writes_marker_heading_and_scores(self):
        number = sample_log.append_sample("A dragon", "Story text.", SCORES, True, path=self.path)
        text = self.path.read_text(encoding="utf-8")
        self.assertEqual(number, 1)
        self.assertIn("<!-- story-log: 1 -->", text)
        self.assertIn("## Sample 1: A dragon (first draft)", text)
        self.assertIn("Age fit 5/5", text)
        self.assertIn("Story text.", text)

    def test_counter_increments_per_entry(self):
        sample_log.append_sample("One", "a", SCORES, True, path=self.path)
        sample_log.append_sample("Two", "b", SCORES, True, path=self.path)
        self.assertEqual(sample_log.count_samples(self.path), 2)

    def test_existing_content_is_preserved(self):
        sample_log.append_sample("One", "a", SCORES, True, path=self.path)
        self.assertTrue(self.path.read_text(encoding="utf-8").startswith("# Existing notes\n\nKeep me.\n"))

    def test_change_entry_records_the_change(self):
        sample_log.append_sample("One", "a", SCORES, True, change="add an owl", path=self.path)
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("(after change: add an owl)", text)
        self.assertIn("**Reader change:** add an owl", text)

    def test_failed_verdict_is_written_honestly(self):
        bad = dict(SCORES, story_arc=2)
        sample_log.append_sample("One", "a", bad, False, path=self.path)
        self.assertIn("stayed below the bar", self.path.read_text(encoding="utf-8"))

    def test_missing_file_counts_as_zero(self):
        self.assertEqual(sample_log.count_samples(Path(self.dir) / "nope.md"), 0)

    def test_marker_inside_sentence_is_not_counted(self):
        self.path.write_text("Each entry starts with a `<!-- story-log: N -->` marker.\n", encoding="utf-8")
        self.assertEqual(sample_log.count_samples(self.path), 0)


class RealSampleFileTests(unittest.TestCase):
    def test_real_file_has_at_least_four_samples(self):
        self.assertGreaterEqual(sample_log.count_samples(REAL_LOG), 4)

    def test_every_counted_sample_has_a_heading(self):
        text = REAL_LOG.read_text(encoding="utf-8")
        self.assertEqual(text.count("\n## Sample "), sample_log.count_samples(REAL_LOG))

    def test_real_file_contains_no_api_key(self):
        self.assertNotIn("sk-ant-api03-", REAL_LOG.read_text(encoding="utf-8"))


class StoryFormattingTests(unittest.TestCase):
    def test_storyteller_is_told_to_use_plain_text(self):
        from prompts import STORYTELLER_SYSTEM
        self.assertIn("Plain text only", STORYTELLER_SYSTEM)

    def test_page_has_inline_bold_and_italic_renderer(self):
        js = Path(__file__).resolve().parent.parent.joinpath("static", "app.js").read_text(encoding="utf-8")
        self.assertIn('el("strong"', js)
        self.assertIn('el("em"', js)
        self.assertNotIn("innerHTML", js)


class PageFreshnessTests(unittest.TestCase):
    def test_page_and_scripts_are_not_cached_stale(self):
        web.app.config["TESTING"] = True
        client = web.app.test_client()
        for path in ("/", "/static/app.js"):
            resp = client.get(path, base_url="http://127.0.0.1:5000")
            self.assertEqual(resp.headers.get("Cache-Control"), "no-cache", path)


class SampleRouteTests(unittest.TestCase):
    def setUp(self):
        web.app.config["TESTING"] = True
        self.client = web.app.test_client()
        self.dir = tempfile.mkdtemp()
        self.path = Path(self.dir) / "samples.md"
        shutil.copy(REAL_LOG, self.path)
        self.patch = mock.patch.object(sample_log, "LOG_PATH", self.path)
        self.patch.start()
        keystore.clear_key()
        web.runs.clear()
        web.recent_calls.clear()
        keystore.set_key(FAKE_KEY)

    def tearDown(self):
        self.patch.stop()
        keystore.clear_key()
        shutil.rmtree(self.dir, ignore_errors=True)

    def base(self, path):
        return self.client.open(path, base_url="http://127.0.0.1:5000", headers=HEADERS,
                                method="POST", data=json.dumps(_body[path]))

    def test_new_story_is_logged_automatically(self):
        before = sample_log.count_samples(self.path)
        with mock.patch.object(web, "make_client", return_value=FakeClient()):
            resp = self.client.post("/api/runs", data=json.dumps({"request": "A sleepy owl"}),
                                    headers=HEADERS, base_url="http://127.0.0.1:5000")
        data = resp.get_json()
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(data["sample_number"], before + 1)
        self.assertEqual(sample_log.count_samples(self.path), before + 1)
        self.assertIn("A sleepy owl", self.path.read_text(encoding="utf-8"))

    def test_change_is_logged_as_new_sample(self):
        with mock.patch.object(web, "make_client", return_value=FakeClient()):
            run = self.client.post("/api/runs", data=json.dumps({"request": "A sleepy owl"}),
                                   headers=HEADERS, base_url="http://127.0.0.1:5000").get_json()
            before = sample_log.count_samples(self.path)
            resp = self.client.post(f"/api/runs/{run['id']}/feedback",
                                    data=json.dumps({"change": "make it shorter"}),
                                    headers=HEADERS, base_url="http://127.0.0.1:5000")
        self.assertEqual(resp.get_json()["sample_number"], before + 1)
        self.assertIn("**Reader change:** make it shorter", self.path.read_text(encoding="utf-8"))

    def test_counter_endpoint_matches_file(self):
        resp = self.client.get("/api/samples", base_url="http://127.0.0.1:5000")
        data = resp.get_json()
        self.assertEqual(data["count"], sample_log.count_samples(self.path))
        self.assertEqual(data["file"], self.path.name)
        self.assertTrue(data["visible"])

    def test_counter_can_be_hidden(self):
        with mock.patch.object(web, "SAMPLE_COUNTER_VISIBLE", False):
            data = self.client.get("/api/samples", base_url="http://127.0.0.1:5000").get_json()
        self.assertFalse(data["visible"])

    def test_story_still_returns_when_log_write_fails(self):
        with mock.patch.object(web, "make_client", return_value=FakeClient()), \
             mock.patch.object(sample_log, "append_sample", side_effect=OSError("disk full")):
            resp = self.client.post("/api/runs", data=json.dumps({"request": "A sleepy owl"}),
                                    headers=HEADERS, base_url="http://127.0.0.1:5000")
        self.assertEqual(resp.status_code, 201)
        self.assertIsNone(resp.get_json()["sample_number"])

    def test_api_key_never_written_to_samples(self):
        with mock.patch.object(web, "make_client", return_value=FakeClient()):
            self.client.post("/api/runs", data=json.dumps({"request": "A sleepy owl"}),
                             headers=HEADERS, base_url="http://127.0.0.1:5000")
        self.assertNotIn(FAKE_KEY, self.path.read_text(encoding="utf-8"))

    def test_log_path_cannot_be_set_from_request(self):
        with mock.patch.object(web, "make_client", return_value=FakeClient()):
            self.client.post("/api/runs", data=json.dumps({"request": "A sleepy owl", "path": "/tmp/x.md"}),
                             headers=HEADERS, base_url="http://127.0.0.1:5000")
        self.assertFalse(Path("/tmp/x.md").exists())
        self.assertIs(sample_log.LOG_PATH, self.path)


_body = {}

if __name__ == "__main__":
    unittest.main()
