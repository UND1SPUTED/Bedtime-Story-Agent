(() => {
  const CLIENT_HEADER = { "X-Story-Client": "1" };
  const CRITERIA = {
    age_fit: "Age fit",
    request_fidelity: "Follows the request",
    story_arc: "Story arc",
    engagement: "Engagement",
    bedtime_calm: "Bedtime calm",
    safety: "Safety",
  };
  const $ = (id) => document.getElementById(id);
  let currentRunId = null;

  function el(tag, props = {}, children = []) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else node.setAttribute(k, v);
    }
    for (const child of [].concat(children)) node.append(child);
    return node;
  }

  async function api(path, method = "GET", body = null) {
    const opts = { method, credentials: "same-origin", headers: { ...CLIENT_HEADER } };
    if (body !== null) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(path, opts);
    let data = {};
    try { data = await res.json(); } catch (_) { /* non-JSON error page */ }
    if (!res.ok) throw new Error(data.error || "Something went wrong. Try again.");
    return data;
  }

  function setBusy(isBusy, message = "") {
    $("ask-submit").disabled = isBusy || !keyIsSet;
    $("change-submit").disabled = isBusy;
    $("skeleton").hidden = !isBusy;
    $("status").textContent = message;
  }

  function showError(id, message) {
    const node = $(id);
    node.textContent = message || "";
    node.hidden = !message;
  }

  let keyIsSet = false;
  function renderKeyStatus(status) {
    keyIsSet = Boolean(status.set);
    const text = keyIsSet
      ? (status.source === "environment"
          ? `Using the key from this computer's environment, ending in ${status.hint}.`
          : `Key saved for this session, ending in ${status.hint}.`)
      : "No key yet. Add one to start writing stories.";
    $("key-status").textContent = text;
    $("key-forget").hidden = !keyIsSet || status.source === "environment";
    $("ask-submit").disabled = !keyIsSet;
  }

  async function loadKeyStatus() {
    try { renderKeyStatus(await api("/api/key")); }
    catch (err) { $("key-status").textContent = "Could not check the key status."; }
  }

  $("key-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = $("key-input");
    const value = input.value.trim();
    input.value = "";
    showError("key-error", "");
    try {
      renderKeyStatus(await api("/api/key", "POST", { key: value }));
    } catch (err) {
      showError("key-error", err.message);
    }
  });

  $("key-forget").addEventListener("click", async () => {
    try { renderKeyStatus(await api("/api/key", "DELETE")); }
    catch (err) { showError("key-error", err.message); }
  });

  const askInput = $("ask-input");
  askInput.addEventListener("input", () => {
    $("ask-count").textContent = `${askInput.value.length} / 500`;
  });
  document.querySelectorAll("[data-example]").forEach((chip) => {
    chip.addEventListener("click", () => {
      askInput.value = chip.dataset.example;
      askInput.dispatchEvent(new Event("input"));
      askInput.focus();
    });
  });

  function inlineNodes(text) {
    const nodes = [];
    const pattern = /\*\*([^*\n]+)\*\*|\*([^*\n]+)\*/g;
    let last = 0;
    let match;
    while ((match = pattern.exec(text)) !== null) {
      if (match.index > last) nodes.push(document.createTextNode(text.slice(last, match.index)));
      nodes.push(match[1] !== undefined
        ? el("strong", { text: match[1] })
        : el("em", { text: match[2] }));
      last = pattern.lastIndex;
    }
    if (last < text.length) nodes.push(document.createTextNode(text.slice(last)));
    return nodes;
  }

  function renderStory(run) {
    const body = $("story-body");
    body.replaceChildren();
    const lines = run.story.split("\n").map((l) => l.trim());
    const [first, ...rest] = lines;
    const plainFirst = first ? first.replace(/\*/g, "").trim() : "";
    let titleUsed = false;
    if (plainFirst && plainFirst.length < 70 && !/[.!?"]$/.test(plainFirst) && rest.some((l) => l)) {
      body.append(el("h2", { text: plainFirst }));
      titleUsed = true;
    }
    const paragraphs = (titleUsed ? rest : lines).join("\n").split(/\n\s*\n/);
    for (const block of paragraphs) {
      const text = block.replace(/\s*\n\s*/g, " ").trim();
      if (text) body.append(el("p", {}, inlineNodes(text)));
    }
  }

  function renderScores(run) {
    const list = $("scores");
    list.replaceChildren();
    const last = run.history[run.history.length - 1];
    for (const [key, label] of Object.entries(CRITERIA)) {
      const score = last.scores[key];
      const bar = el("span", {});
      bar.style.width = `${(score / 5) * 100}%`;
      if (score < 4) bar.className = "low";
      list.append(el("li", { class: "score-row" }, [
        el("span", { text: label }),
        el("span", { class: "bar", "aria-hidden": "true" }, bar),
        el("span", { class: "score-num", text: `${score}/5` }),
      ]));
    }
    const rounds = run.history.length - 1;
    const plural = rounds === 1 ? "revision" : "revisions";
    const failing = Object.keys(CRITERIA).filter((k) => last.scores[k] < 4).map((k) => CRITERIA[k]);
    $("verdict").textContent = last.passed
      ? (rounds ? `Every criterion met the bar of 4 or higher after ${rounds} ${plural}.` : "Every criterion met the bar of 4 or higher on the first draft.")
      : `Still below the bar on ${failing.join(", ")} after ${rounds} ${plural}.`;
  }

  function renderTrace(run) {
    const container = $("trace");
    container.replaceChildren();
    $("trace-count").textContent = `(${run.trace.length})`;
    run.trace.forEach((call, index) => {
      const meta = `${index + 1}. ${call.stage} · ${call.model} · up to ${call.max_tokens} tokens`;
      container.append(el("details", { class: "call" }, [
        el("summary", { text: meta }),
        el("div", { class: "call-body" }, [
          el("h4", { text: "System prompt" }), el("pre", { text: call.system }),
          el("h4", { text: "User prompt" }), el("pre", { text: call.prompt }),
          el("h4", { text: "Output" }), el("pre", { text: call.output }),
        ]),
      ]));
    });
  }

  function renderSampleCounter(data, run) {
    const node = $("sample-counter");
    node.hidden = !data.visible;
    if (!data.visible) return;
    let note = "";
    if (run && run.sample_number) note = ` · this story is Sample ${run.sample_number}`;
    else if (run) note = " · this story was not logged";
    node.textContent = `Samples in ${data.file}: ${data.count}${note}`;
  }

  async function loadSampleCounter(run = null) {
    try { renderSampleCounter(await api("/api/samples"), run); }
    catch (err) { $("sample-counter").hidden = true; }
  }

  function renderRun(run) {
    currentRunId = run.id;
    $("empty").hidden = true;
    $("result").hidden = false;
    renderStory(run);
    renderScores(run);
    renderTrace(run);
    $("change-input").value = "";
  }

  $("ask-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = askInput.value.trim();
    if (!text) return;
    showError("ask-error", "");
    setBusy(true, "Writing a first draft and checking it. This takes about a minute.");
    try {
      const run = await api("/api/runs", "POST", { request: text });
      renderRun(run);
      setBusy(false, "Story ready.");
      loadSampleCounter(run);
    } catch (err) {
      setBusy(false, "");
      showError("ask-error", err.message);
    }
  });

  $("change-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const change = $("change-input").value.trim();
    if (!change || !currentRunId) return;
    showError("change-error", "");
    setBusy(true, "Applying your change and checking it again.");
    try {
      const run = await api(`/api/runs/${encodeURIComponent(currentRunId)}/feedback`, "POST", { change });
      renderRun(run);
      setBusy(false, "Change applied.");
      loadSampleCounter(run);
    } catch (err) {
      setBusy(false, "");
      showError("change-error", err.message);
    }
  });

  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
  function selectTab(name) {
    tabs.forEach((tab) => {
      const active = tab.dataset.tab === name;
      tab.setAttribute("aria-selected", String(active));
      tab.tabIndex = active ? 0 : -1;
    });
    $("panel-write").hidden = name !== "write";
    $("panel-prompts").hidden = name !== "prompts";
    if (name === "prompts") loadPrompts();
  }
  tabs.forEach((tab, i) => {
    tab.addEventListener("click", () => selectTab(tab.dataset.tab));
    tab.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        const next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
        next.focus();
        selectTab(next.dataset.tab);
      }
    });
  });

  let promptsLoaded = false;
  async function loadPrompts() {
    if (promptsLoaded) return;
    try {
      const data = await api("/api/prompts");
      const list = $("prompt-list");
      list.replaceChildren();
      for (const p of data.prompts) {
        list.append(el("section", { class: "prompt-card" }, [
          el("h2", { text: p.name }),
          el("p", { class: "muted", text: p.description }),
          el("pre", { text: p.text }),
        ]));
      }
      promptsLoaded = true;
    } catch (err) {
      $("prompt-list").textContent = "Could not load the prompts. Refresh the page.";
    }
  }

  loadKeyStatus();
  loadSampleCounter();
})();
