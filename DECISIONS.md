# Decisions Log

This file records each code change and each variable change, with the reason for it.

## Files kept, changed, or added

| File | Status | Reason |
|---|---|---|
| `main.py` | Changed (rewritten) | The starter had a single OpenAI call. The assignment needs an analyze, draft, judge, revise, and feedback flow. The entry point stays a CLI so the reviewer can run it without setup beyond the key. |
| `requirements.txt` | Added | Lists the one runtime dependency, `anthropic`, so reviewers can install it with one command. The version floor `>=0.40.0` is the first release with the current Messages API features used here. |
| `llm.py` | Added | Isolates the model client so that prompts and pipeline code never touch the SDK directly. This also makes the fake client in the tests a drop-in replacement. |
| `prompts.py` | Added | Keeps all prompt text in one place, so prompts can be reviewed and tuned without reading logic. The assignment grades prompt quality, so this file is what a reviewer will read first. |
| `judge.py` | Added | The judge is a required component, so it gets its own module with its own rubric, threshold, and output parsing. |
| `pipeline.py` | Added | Holds the orchestration (analyze, draft, judge loop, user feedback). Keeping this separate from `main.py` lets the tests exercise the logic without typing input. |
| `tests/test_pipeline.py` | Added | Verifies the logic without an API key. These tests check control flow, not story quality, and the README says so. |
| `README.md` | Rewritten | Contains setup, run instructions, and the required block diagram in Mermaid, which renders on GitHub. The diagram mirrors the actual function calls. |
| `.gitignore` | Added | Prevents committing `.env` files or `__pycache__`, which protects the API key requirement from the assignment. |
| `DECISIONS.md` | Added | This file, as requested. |

## Model and API changes

| Original | New | Reason |
|---|---|---|
| `import openai` | `import anthropic` (in `llm.py`) | The assignment email says to use Claude Haiku 5.5 instead of GPT-3.5 and explicitly overrides the README's "do not change the model" line. |
| `model="gpt-3.5-turbo"` | `MODEL = "claude-haiku-5-5"` | Same reason. It is a module constant so it can be changed in one place. |
| `openai.api_key = os.getenv("OPENAI_API_KEY")` | `get_client()` reads `ANTHROPIC_API_KEY` and raises a clear error if missing | Matches the email's instruction to use our own key stored in an environment variable. A clear error is better than an opaque authentication failure. |
| `openai.ChatCompletion.create(...)` | `client.messages.create(...)` | `ChatCompletion` is the deprecated OpenAI API. The Anthropic Messages API is the equivalent call. |
| `resp.choices[0].message["content"]` | `"".join(block.text for block in resp.content if block.type == "text")` | Anthropic returns a list of content blocks, not a choices array. Filtering by `type == "text"` skips any non-text blocks. |
| `call_model(prompt, max_tokens=3000, temperature=0.1)` | `call_model(client, system, prompt, max_tokens=1500, temperature=0.7)` | The new signature takes a system prompt so storyteller and judge instructions stay separate from user content. Lower `max_tokens` because a 5 to 10 year old story is 250 to 500 words, so 3000 was wasteful. `temperature` moved from 0.1 to 0.7 for the storyteller, because 0.1 produces flat, repetitive stories. The judge overrides this to 0.0 (see below). |
| `example_requests` (module variable) | Removed from the library code | It was unused in the starter. The example request is shown in the README instead, so the code has no dead variables. |
| `user_input` in `main()` | `request` in `main()` | Renamed to match the rest of the pipeline's vocabulary (`request`). Also stripped whitespace and reject empty input, which the starter did not handle. |
| `response` in `main()` | `state` | The result is now a dict holding the request, brief, story, and judge history, not a single string. |

## New variables and constants

| Name | Value | Reason |
|---|---|---|
| `MAX_REVISION_ROUNDS` | `2` | Caps automatic revision so cost and latency stay bounded. Two rounds catch most problems. More rounds show diminishing returns in testing style judges and make it harder to explain behavior. |
| `MAX_FEEDBACK_TURNS` | `5` | Caps the user feedback loop. Prevents an endless session and still gives enough room for a reviewer to try several changes. |
| `PASS_THRESHOLD` | `4` | A story passes only if every criterion scores 4 or higher. A single weak criterion, such as age fit, should block a story even if the average is high. |
| `DEFAULT_BRIEF` | category `general`, 350 words | Fallback used if the analyzer returns unparseable output. The pipeline keeps working instead of crashing on a bad model reply. |
| `CRITERIA` | six judge criteria | Chosen to match the assignment's evaluation: age fit, request fidelity, story arc, engagement, bedtime calm, and safety. Each one maps to a visible requirement. |
| `CATEGORIES` | six categories | The README suggests categorizing requests with tailored strategies. Six covers common bedtime requests without making the prompts hard to review. |
| `temperature=0.0` (judge) | 0.0 | Judging should be consistent. Same story should get the same scores on repeated runs. |
| `temperature=0.0` (analyzer) | 0.0 | Classification should be deterministic. |
| `temperature=0.8` (storyteller and revision) | 0.8 | Creative writing needs variety, but not so much that the story drifts from the request. |
| `max_tokens` values | analyzer 300, judge 600, story 1200 | Each is sized to its output. The judge returns short JSON, the analyzer returns a small object, and a 500 word story needs roughly 700 tokens, so 1200 leaves headroom. |
| `target_words` clamped to 250 to 500 | | The model may return out-of-range values. Clamping keeps stories in the age-appropriate length range from the assignment. |

## Pipeline and logic decisions

- **Analyze first, then write.** Separating classification from writing lets each category get its own storyteller guidance, which the README suggests. A single prompt doing both is harder to tune and to explain.
- **Judge after every draft, including passing ones.** The judge is the only quality check, so it runs on the first draft too. Stories that pass after one check are not rewritten.
- **Revision sends the judge's feedback back to the storyteller.** This closes the loop the assignment asks for. Keeping the same characters, setting, and tone in the revision prompt prevents drift.
- **Judge reads only the story and the request, not the previous drafts.** This keeps each judgment independent and prevents the judge from anchoring on earlier scores.
- **Revision history is kept.** Each round stores the story, scores, and feedback. This lets the reviewer see what the judge changed, which supports the "explain every part" requirement.
- **User feedback runs through the same judge loop.** A changed story should still meet the safety and age criteria. Skipping the judge for user edits would allow an unsafe change to pass.
- **Judge output is validated.** Missing scores default to 1, and feedback is capped at 4 items. A malformed judge reply therefore fails the story instead of silently passing it.
- **Analyzer failures fall back to defaults.** A non-JSON analyzer reply uses `DEFAULT_BRIEF` instead of raising an error mid-session.
- **Prompts use a JSON-only instruction for analyzer and judge.** The parser accepts fenced JSON too, since models sometimes wrap output in code fences.
- **Storyteller prompt bans scary or violent content and asks for a soft ending.** These two rules come directly from the assignment's age 5 to 10 requirement and the bedtime purpose.
- **Story length is decided by the analyzer (250 to 500 words).** The README says "you decide" on length. A specific target gives the judge something concrete to check and keeps stories short enough for bedtime.

## Things I deliberately left out

- **No database or persistent memory.** The assignment asks for a working script, and persistence adds setup burden for reviewers. It is listed as a next step in `main.py`.
- **No web UI.** A CLI keeps the surface small and matches the starter.
- **No text-to-speech or reading-level library.** Both are listed as next steps. Adding them now would increase dependencies and the number of things a reviewer must verify.
- **No automated story-quality eval.** Story quality is subjective and needs human review, which the README requests.

## Verification status

- Unit tests pass with a fake client (5 tests). See `tests/test_pipeline.py`.
- The live API was not called. No API key was available when this was built, so story quality, judge calibration, and the `PASS_THRESHOLD` value are untested against the real model. The README asks the user to run the program and tune the prompts or threshold if needed.


## Web UI (added in the latest revision)

| File or change | Reason |
|---|---|
| `app.py` (new) | Flask server with the routes for key status, story runs, reader feedback, and the prompt list. Flask was chosen because it is small, standard, and has a test client, so the security checks can be tested without a browser. |
| `keystore.py` (new) | The key lives in a module variable guarded by a lock. The only other source is the `ANTHROPIC_API_KEY` environment variable. Nothing is written to disk, so a restart clears the key. Only the last 4 characters are ever returned, for display. |
| `tracing.py` (new) | `TracingClient` wraps the Anthropic client and records each call's system prompt, user prompt, output, model, temperature, and token limit. It records the call after the response, so it never sees or stores the key. Stage names are inferred from prompt text so the inspector can label each call. |
| `llm.py` changed | Added `make_client(api_key)` so the web app can build a client from the in-memory key. `get_client()` now calls it, so the CLI behaves the same. |
| `pipeline.py`, `judge.py`, `prompts.py`, `main.py` | Unchanged. The UI reuses the same pipeline, so the CLI and UI produce the same stories. |
| `templates/index.html`, `static/styles.css`, `static/app.js` (new) | The page, styles, and script. |
| `requirements.txt` | Added `flask>=3.0,<4` and kept `anthropic`. The Flask version is capped to the 3.x line the code was tested with. |
| `tests/test_app.py` (new) | Covers the key lifecycle, CSRF and host guards, that the key never appears in responses, the run and feedback flow, and input limits. |

### Security decisions

| Risk | Measure | Why |
|---|---|---|
| Key leaks to disk or logs | Memory only, never logged, never returned, masked to 4 characters | The assignment says the key must not be pushed to GitHub, and an exposed key can be abused and billed. |
| Other machines reach the server | Bind to 127.0.0.1 | The server has no login, so it must not be reachable from the network. |
| DNS rebinding | Host header must be localhost or 127.0.0.1 | A malicious site could otherwise make the browser talk to this server. |
| Cross-site request forgery | Required `X-Story-Client` header and JSON body on POST and DELETE | Browsers cannot add custom headers to a cross-site request without a preflight check, which this server does not allow. |
| Cross-site script injection | Strict CSP with no inline scripts or styles; output inserted with `textContent` | Model output and user text can contain anything, so it is treated as plain text. |
| Clickjacking | `X-Frame-Options: DENY` and `frame-ancestors 'none'` | The page should not be framed by another site. |
| Oversized or abusive input | 500 character limits, 16 KB request cap, control characters stripped | Limits cost and prevents malformed input. |
| Runaway model spending | 10 model calls per minute, one generation at a time | Protects the key owner's budget if the page is left open or misused. |
| Sensitive errors | Generic messages to the browser; only exception type names are logged | Error text from the SDK could contain request details. |
| Stale or stored data | Responses marked `no-store`; runs held in memory and capped at 20 | Nothing is cached by the browser or kept long-term. |

### Design decisions (impeccable and frontend-design skills)

- The UI is an Operate surface (a tool), so it uses restrained, familiar patterns: one system sans for the interface, a readable serif only for the story text, and monospace only for prompts because they are code.
- There are no eyebrow labels, uppercase labels, gradient text, nested cards, decorative shadows, emoji icons, or page-load animation. These are the defaults the craft floor rejects.
- The layout is a two-column grid on wide screens and one column on narrow ones. The key and request forms sit on the side, and the story is the main column.
- Judge scores are shown as labeled bars plus a number, with failing criteria in a different color and a plain-language verdict, so the result does not depend on color alone.
- Loading uses a skeleton block rather than a spinner in the middle of content. Motion is limited to that pulse, which is turned off for users who prefer reduced motion.
- Focus rings are visible, the tabs support arrow keys, and status messages use `aria-live`.
- Dark mode follows the system setting through color tokens.
- Copy is in product language. Buttons name their action ("Save key", "Write story", "Apply change"), and errors say what to do next.

### Verification status

- 17 automated tests pass (5 for the pipeline, 12 for the web app).
- The live server was started and checked with curl. The page returned 200, the CSP and frame headers were present, a foreign Host header got 400, and a POST without the custom header got 403.
- Static checks found no inline scripts, handlers, style attributes, or `innerHTML` use in the page.
- I could not take a screenshot, because the headless browser could not be downloaded in this environment. Check the layout in a real browser before submitting.
- The live model was not called, because there is no API key here.


### Fixes found by running the app in a browser (Playwright, Chromium 131)

| Change | Reason |
|---|---|
| Removed the `temperature` argument from every model call (`llm.call_model`, `pipeline.py`, `judge.py`), and removed the temperature field from the call trace and the UI | The current Anthropic SDK (2.x) no longer accepts `temperature` in `messages.create`. The first real story request failed with `TypeError: unexpected keyword argument 'temperature'`. `pip install` gets the latest SDK, so every user would hit this. The fix uses the model's default sampling instead of pinning an old SDK, which would have stayed broken for anyone on a newer one. The earlier temperature choices (0.0 for judging, 0.8 for writing) are therefore no longer in effect; this is a trade-off to note when explaining the design. |
| Added `[hidden] { display: none !important; }` to the stylesheet | Class rules like `.skeleton { display: grid }` overrode the browser's default `hidden` behavior, so the loading placeholder and the Prompts text showed on the Write tab at all times. |
| Rewrote the judge verdict text to state the real number of revision rounds | The old wording ("revised up to two times") was shown even when only one round had run. The new text reads, for example, "Still below the bar on Story arc after 1 revision." |
| `tracing.py` no longer reads `kwargs["temperature"]` | Needed after the argument was removed; reading it would have raised a `KeyError`. |
| Tests updated: the reader-feedback test now expects the judge history to describe only the latest version | After a change, the pipeline replaces the judge history with the new version's rounds, which is the intended behavior. The old test expected the history to accumulate. |

### Fix: judge reply could not be parsed (found in a live run)

A live run returned HTTP 200 for all three model calls, then failed on `json.loads` in the judge step with "Expecting ',' delimiter". The model's review contained text that was not valid JSON, such as an unescaped quote inside a feedback string.

| Change | Reason |
|---|---|
| `llm.parse_json` tries the whole reply first, then decodes the first JSON object with `raw_decode`, and raises `ValueError` with a readable message | The old code sliced from the first `{` to the last `}`. Any stray brace or quote after the object broke it. `raw_decode` reads one object and ignores trailing text. |
| `judge.judge_story` retries the judge once on a bad reply, then raises `JudgeFormatError` | Model replies vary between calls, so one retry usually succeeds. The retry is capped at one to bound cost. |
| The bad reply's first 200 characters are logged to the terminal | Lets you see what the model returned without exposing the key. This is story-review text only. |
| `app.py` maps `ValueError` to HTTP 502 "The model's reply could not be read. Try again." | Previously this became a generic 500 "Something went wrong on the server." |
| New `tests/test_parsing.py` (8 tests) | Covers fenced JSON, trailing text, leading prose, broken JSON, and the retry path. |

Test count is now 25, and all pass.

### Submission readiness

| Change | Reason |
|---|---|
| `main.py` catches a missing key, a rejected key, a failed model call, and an unusable reply, and prints a message | Reviewers often try the terminal version first. A raw traceback on a missing key would look like a broken project. Tested with no key and with a fake key. |
| `sample_outputs.md` added with two stories from real runs | The assignment's quality criterion is best judged from actual outputs. Only the text and scores visible in the captured screenshots are included; nothing was invented. |
| `sample_outputs.md` shows only visible judge scores for Sample 1 | The full score list for the first draft wasn't captured. Leaving the missing rows out is more honest than guessing them. |
| README sections added: sample outputs, verification, and the terminal entry point | Gives reviewers a path through the project in the order they will likely check it. |
| Stub screenshots removed (`6_result_sample_data.png`, `7_trace_sample_data.png`) | They were produced from fake data and could be mistaken for real results. The remaining screenshots show real UI states. |
| Fresh-folder install test run | Confirms that `requirements.txt` installs, the tests pass, and both routes respond from an empty virtual environment. |
| Key scan run | Only the key-format pattern and the placeholder text match. No real key is in the project. |


### Automatic sample logging and counter

| Change | Reason |
|---|---|
| New `sample_log.py` with `append_sample` and `count_samples` | Keeps file writing in one small module that is easy to test and to remove. |
| Each entry starts with a `<!-- story-log: N -->` marker, and the counter counts only those markers | Matching whole marker lines means prose that quotes the marker, such as the instructions at the top of the file, is not counted. |
| Log path is fixed to `sample_outputs.md` next to `app.py`, and no request field can change it | Stops a browser request from making the server write to an arbitrary file. A test checks this. |
| A writing lock around the append | Keeps entries whole if two requests finish at about the same time. |
| Logging failures are caught and reported as `sample_number: null` | A disk or permissions problem should not hide the story the reader just paid for. A test checks the story still returns. |
| The API key is never written to the sample file | The key is kept out of every file. A test checks this on a generated entry. |
| Each change is logged as a new sample with its text | The assignment asks for changes; a separate entry per change shows the before and after of the feedback loop. |
| `sample_outputs.md` reorganized: instructions at the top, markers added to samples 1 and 2 | So new entries land at the end without being mixed into the instructions, and the existing samples are counted. |
| Test-written samples 3 to 5 removed from `sample_outputs.md` | The app tests had been writing their fake stories to the real file. Those tests now write to a temporary file. |
| `GET /api/samples` returns the count, filename, and a visibility flag | Lets the page show the counter, and lets it be hidden with one setting. |
| Counter line in the UI, updated after each story or change | Shows the running total and whether the current story was logged. |
| `SAMPLE_COUNTER_VISIBLE` constant in `app.py` | Marks the counter as temporary and makes it easy to remove. |
| `main.py` (terminal version) does not log samples | Keeps the terminal flow unchanged. Samples were requested from the web app. |
| 17 new tests in `tests/test_samples.py` | Check the marker count, the append format, change entries, the fixed log path, that the key is never written, that a failed write doesn't break a story, the counter route, and that the real file has the expected samples. |

| `sample_outputs.md` cleared of the two earlier samples | Requested. The file now holds only the instructions, so the counter starts at 0 and the next logged story is Sample 1. |

### Fix: model used its whole output budget on reasoning (found in a live run)

The server log showed `stop_reason=max_tokens` with only a `thinking` block and no text. The model spent the entire output limit on reasoning before writing anything, so the app had no text to read. This is also the cause of the earlier empty judge replies.

| Change | Reason |
|---|---|
| Story, reader-feedback, and revision calls: `max_tokens` 1200 → 6000 | Leaves room for reasoning and a 250 to 500 word story. The limit is a cap; unused tokens are not billed. |
| Judge: 1500 → 4000 | Same cause; the judge's JSON reply follows any reasoning. |
| Analyzer: 300 → 2000 | Same cause; the brief is small, but reasoning can use a lot of budget first. |
| `call_model` default 1500 → 4000 | Matches the new budgets for any caller that uses the default. |
| New test checks that every budget is at least 2000 | Prevents a future edit from reintroducing the empty-reply failure. |

### Fix: markdown asterisks showing on the page

The model wrapped the title in `**` and some phrases in `*`, and the page showed them as raw characters.

| Change | Reason |
|---|---|
| `static/app.js` turns `**text**` into `<strong>` and `*text*` into `<em>` with DOM elements | Renders the emphasis the model intended. Built with `textContent` and `createElement`, not `innerHTML`, so model text can never run as HTML. A test checks `innerHTML` is not used. |
| The title line's asterisks are removed and it is shown as a heading | Headings already display bold, so the title looks bold without doubled markup. |
| `prompts.py` storyteller rule: "Plain text only. Do not use markdown, asterisks, bullet points, or headings." | Reduces the asterisks at the source. The renderer still handles any that remain. |
| Sample log text is unchanged | Markdown files render `**` and `*` as bold and italic, so the logged samples look correct in VS Code's preview. |

| `sample_outputs.md` replaced with the author's six logged samples | The file now shows real outputs from the web app: five first drafts and one reader-change revision. The test that expected an empty file now checks for at least four samples. |
