import logging
import re
import secrets
import threading
import time
from collections import OrderedDict, deque
from urllib.parse import urlparse

import anthropic
from flask import Flask, abort, jsonify, render_template, request

import keystore
from llm import make_client
from pipeline import apply_user_feedback, generate_story
from prompts import (
    ANALYZER_PROMPT,
    ANALYZER_SYSTEM,
    CATEGORIES,
    JUDGE_PROMPT,
    JUDGE_SYSTEM,
    REVISER_PROMPT,
    STORY_BRIEF,
    STORYTELLER_SYSTEM,
    USER_FEEDBACK_PROMPT,
)
from tracing import TracingClient
import sample_log

HOST, PORT = "127.0.0.1", 5000
ALLOWED_HOSTNAMES = {"127.0.0.1", "localhost"}
MAX_REQUEST_CHARS = 500
MAX_FEEDBACK_CHARS = 500
MAX_STORED_RUNS = 20
SAMPLE_COUNTER_VISIBLE = True  # temporary: set to False to hide the sample counter in the UI
RATE_LIMIT_CALLS = 10
RATE_LIMIT_WINDOW_SECONDS = 60
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

log = logging.getLogger("bedtime_story")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
app.config["JSON_SORT_KEYS"] = False

runs: "OrderedDict[str, dict]" = OrderedDict()
runs_lock = threading.Lock()
work_lock = threading.Lock()
recent_calls: deque = deque()
PROMPTS = [
    ("Request analyzer (system)", "Sets the model's role for classifying a request.", ANALYZER_SYSTEM),
    ("Request analyzer", "Turns the request into a brief: category, characters, setting, tone, length.", ANALYZER_PROMPT),
    ("Storyteller (system)", "Story-writing rules for ages 5 to 10. Shared by every storyteller call.", STORYTELLER_SYSTEM),
    ("Story brief", "Fills the first draft with the analyzer's brief.", STORY_BRIEF),
    ("Judge (system)", "Sets the model's role as a strict editor for the rubric.", JUDGE_SYSTEM),
    ("Judge", "Six-criterion rubric with 1 to 5 scores and feedback.", JUDGE_PROMPT),
    ("Reviser", "Rewrites a draft using the judge's feedback.", REVISER_PROMPT),
    ("Reader feedback rewrite", "Applies a change the reader asks for, then goes back through the judge.", USER_FEEDBACK_PROMPT),
]


def _clean(text) -> str:
    if not isinstance(text, str):
        return ""
    return CONTROL_CHARS.sub("", text).strip()


def _host_ok(url_or_host: str) -> bool:
    host = urlparse(url_or_host).hostname if "://" in url_or_host else url_or_host.split(":")[0]
    return host in ALLOWED_HOSTNAMES


@app.before_request
def guard_host_and_origin():
    if not _host_ok(request.host):
        abort(400)
    origin = request.headers.get("Origin")
    if origin and not _host_ok(origin):
        abort(403)
    if request.method in ("POST", "DELETE") and request.path.startswith("/api/"):
        if request.headers.get("X-Story-Client") != "1":
            abort(403)
        if request.method == "POST" and not request.is_json:
            abort(415)


@app.after_request
def security_headers(resp):
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
        "form-action 'self'; frame-ancestors 'none'"
    )
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    elif request.path == "/" or request.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


def _error(message: str, status: int):
    return jsonify({"error": message}), status


def _allow_model_call() -> bool:
    now = time.monotonic()
    with runs_lock:
        while recent_calls and now - recent_calls[0] > RATE_LIMIT_WINDOW_SECONDS:
            recent_calls.popleft()
        if len(recent_calls) >= RATE_LIMIT_CALLS:
            return False
        recent_calls.append(now)
        return True


def _log_sample(state: dict, change=None):
    last = state["history"][-1]
    try:
        return sample_log.append_sample(
            state["request"], state["story"], last["scores"], last["passed"], change=change
        )
    except OSError as exc:
        log.warning("sample log not written: %s", type(exc).__name__)
        return None


def _serialize(run: dict) -> dict:
    state = run["state"]
    return {
        "id": run["id"],
        "sample_number": run.get("sample_number"),
        "request": state["request"],
        "brief": state["brief"],
        "story": state["story"],
        "history": [
            {"scores": h["scores"], "feedback": h["feedback"], "passed": h["passed"]}
            for h in state["history"]
        ],
        "trace": run["trace"],
    }


def _run_model_job(job):
    key = keystore.current_key()
    if not key:
        return _error("Add your Anthropic API key first.", 401)
    if not _allow_model_call():
        return _error("Too many requests in a short time. Wait a minute and try again.", 429)
    try:
        with work_lock:
            return job(key)
    except anthropic.AuthenticationError:
        return _error("Anthropic rejected this key. Check it and add it again.", 401)
    except ValueError as exc:
        log.warning("model output could not be used: %s", exc)
        return _error("The model's reply could not be read. Try again.", 502)
    except anthropic.RateLimitError:
        return _error("Anthropic's rate limit was reached. Wait a minute and try again.", 429)
    except anthropic.APIError as exc:
        log.warning("model request failed: %s", type(exc).__name__)
        return _error("The model request failed. Try again in a moment.", 502)
    except Exception as exc:
        log.exception("unexpected failure: %s", type(exc).__name__)
        return _error("Something went wrong on the server. Try again.", 500)


def _store_run(state: dict, trace: list) -> dict:
    run_id = secrets.token_urlsafe(12)
    run = {"id": run_id, "state": state, "trace": trace}
    with runs_lock:
        runs[run_id] = run
        while len(runs) > MAX_STORED_RUNS:
            runs.popitem(last=False)
    return run


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/prompts")
def prompts():
    return jsonify({
        "prompts": [{"name": n, "description": d, "text": t} for n, d, t in PROMPTS],
        "categories": CATEGORIES,
    })


@app.get("/api/samples")
def sample_counter():
    return jsonify({
        "count": sample_log.count_samples(),
        "file": sample_log.LOG_PATH.name,
        "visible": SAMPLE_COUNTER_VISIBLE,
    })


@app.get("/api/key")
def get_key_status():
    return jsonify(keystore.status())


@app.post("/api/key")
def set_key():
    body = request.get_json(silent=True) or {}
    value = _clean(body.get("key"))
    try:
        keystore.set_key(value)
    except ValueError as exc:
        return _error(str(exc), 400)
    return jsonify(keystore.status())


@app.delete("/api/key")
def clear_key():
    keystore.clear_key()
    return jsonify(keystore.status())


@app.post("/api/runs")
def create_run():
    body = request.get_json(silent=True) or {}
    text = _clean(body.get("request"))
    if not text:
        return _error("Describe the story you want first.", 400)
    if len(text) > MAX_REQUEST_CHARS:
        return _error(f"Keep the request under {MAX_REQUEST_CHARS} characters.", 400)

    def job(key):
        trace: list = []
        client = TracingClient(make_client(key), trace)
        state = generate_story(client, text)
        run = _store_run(state, trace)
        run["sample_number"] = _log_sample(state)
        return jsonify(_serialize(run)), 201

    return _run_model_job(job)


@app.post("/api/runs/<run_id>/feedback")
def add_feedback(run_id: str):
    with runs_lock:
        run = runs.get(run_id)
    if run is None:
        return _error("That story is no longer available. Write a new one.", 404)
    body = request.get_json(silent=True) or {}
    change = _clean(body.get("change"))
    if not change:
        return _error("Describe the change you want.", 400)
    if len(change) > MAX_FEEDBACK_CHARS:
        return _error(f"Keep the change under {MAX_FEEDBACK_CHARS} characters.", 400)

    def job(key):
        client = TracingClient(make_client(key), run["trace"])
        with runs_lock:
            run["state"] = apply_user_feedback(client, run["state"], change)
        run["sample_number"] = _log_sample(run["state"], change=change)
        return jsonify(_serialize(run)), 200

    return _run_model_job(job)


@app.get("/api/runs/<run_id>")
def get_run(run_id: str):
    with runs_lock:
        run = runs.get(run_id)
    if run is None:
        return _error("That story is no longer available.", 404)
    return jsonify(_serialize(run))


if __name__ == "__main__":
    print(f"Sample log file: {sample_log.LOG_PATH}")
    app.run(host=HOST, port=PORT, debug=False)
