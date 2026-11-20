"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const ResearchOutcomes = require("../app/static/outcome.js");

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function response(body) {
  return { ok: true, headers: { get: () => "application/json" }, json: async () => body };
}

async function browser() {
  const nodes = new Map(), timeouts = new Map(), calls = [];
  let nextTimer = 0, handler;
  const makeNode = () => ({ value: "", textContent: "", hidden: false, disabled: false,
    dataset: {}, children: [], classList: { toggle() {}, add() {}, remove() {} },
    addEventListener() {}, setAttribute() {}, removeAttribute() {},
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = children; },
  });
  const node = selector => {
    if (!nodes.has(selector)) nodes.set(selector, makeNode());
    return nodes.get(selector);
  };
  const context = vm.createContext({
    console, ResearchOutcomes, URLSearchParams, FormData, Date,
    document: { querySelector: node, querySelectorAll: () => [], createElement: makeNode,
      createTextNode: value => ({ textContent: value }) },
    Option: function(label, value) { return { label, value }; },
    localStorage: { getItem() {}, setItem() {} },
    window: { addEventListener() {} }, location: { search: "" }, history: { replaceState() {} },
    setTimeout(callback, ms) { const id = ++nextTimer; timeouts.set(id, { callback, ms }); return id; },
    clearTimeout(id) { timeouts.delete(id); }, setInterval() { return ++nextTimer; }, clearInterval() {},
    async fetch(url, options) {
      calls.push({ url, options });
      const overridden = handler?.(url, options);
      if (overridden !== undefined) return overridden;
      if (url === "/api/status") return response({ configured: false });
      if (url === "/api/collections") return response({ collections: [] });
      if (url === "/api/runs") return response({ runs: [] });
      throw new Error(`Unexpected request ${url}`);
    },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../app/static/app.js"), "utf8"), context);
  await new Promise(resolve => setImmediate(resolve));
  calls.length = 0;
  return { node, calls, timeouts, run: code => vm.runInContext(code, context),
    handle: callback => { handler = callback; } };
}

test("slow history response cannot replace the record selected more recently", async () => {
  const ui = await browser(), a = deferred(), b = deferred();
  ui.handle(url => url === "/api/runs/a" ? a.promise : url === "/api/runs/b" ? b.promise : undefined);
  const first = ui.run("openRun('a')"), second = ui.run("openRun('b')");
  b.resolve(response({ id: "b", question: "Second question", status: "completed" }));
  await second;
  a.resolve(response({ id: "a", question: "First question", status: "completed" }));
  await first;
  assert.equal(ui.run("state.runId"), "b");
  assert.equal(ui.node("#question").value, "Second question");
});

test("new submission cannot cancel the previously viewed task while awaiting its ID", async () => {
  const ui = await browser(), submission = deferred();
  ui.node("#question").value = "A new question";
  ui.node("#mode").value = "no_tools";
  ui.run("state.runId = 'old'");
  ui.handle(url => url === "/api/research" ? submission.promise : undefined);
  const pending = ui.run("startResearch({ preventDefault() {} })");
  assert.equal(ui.run("state.runId"), null);
  assert.equal(ui.node("#cancel-run").disabled, true);
  await ui.run("cancelResearch()");
  assert.equal(ui.calls.filter(c => c.url.endsWith("/cancel")).length, 0);
  submission.reject(new Error("Offline"));
  await pending;
});

test("obsolete polling response cannot schedule another polling loop", async () => {
  const ui = await browser(), pending = deferred();
  ui.handle(url => url === "/api/runs/a" ? pending.promise : undefined);
  ui.run("beginRunView('a')");
  const poll = ui.run("pollRun()");
  ui.run("beginRunView('a')");
  pending.resolve(response({ id: "a", status: "running" }));
  await poll;
  assert.equal(ui.timeouts.size, 0);
});

test("opening the currently running task does not duplicate polling requests", async () => {
  const ui = await browser();
  ui.run("beginRunView('a'); setRunning(true)");
  await ui.run("openRun('a')");
  assert.equal(ui.calls.length, 0);
});

test("oversized batches and files fail before uploading", async () => {
  const ui = await browser();
  ui.node("#collection").value = "a";
  await ui.run("uploadFiles(Array.from({length: 21}, () => ({name: 'test.txt', size: 1})))");
  assert.match(ui.node("#toast").textContent, /20/);
  await ui.run("uploadFiles([{name: 'test.txt', size: 10000001}])");
  assert.match(ui.node("#toast").textContent, /10 MB/);
  assert.equal(ui.calls.length, 0);
});

test("late cancellation acknowledgement cannot overwrite a completed outcome", async () => {
  const ui = await browser(), pending = deferred();
  ui.handle(url => url.endsWith("/cancel") ? pending.promise : undefined);
  ui.run("beginRunView('a'); setRunning(true)");
  const cancel = ui.run("cancelResearch()");
  ui.run("setRunning(false)");
  ui.node("#progress-message").textContent = "Completed outcome";
  pending.resolve(response({ cancellation_requested: true }));
  await cancel;
  assert.equal(ui.node("#progress-message").textContent, "Completed outcome");
});

test("missing model configuration is actionable and does not leave a submitting state", async () => {
  const ui = await browser();
  ui.node("#question").value = "A research question";
  ui.node("#mode").value = "no_tools";
  ui.handle(url => url === "/api/research" ? { ...response({detail: "Configure LLM_API_KEY in the local .env file"}), ok: false } : undefined);
  await ui.run("startResearch({ preventDefault() {} })");
  assert.equal(ui.run("state.isRunning"), false);
  assert.equal(ui.node("#progress-title").textContent, "研究未能启动");
  assert.match(ui.node("#error-message").textContent, /生成模型尚未配置/);
  assert.equal(ui.node("#run-button").disabled, false);
});

test("upstream quota and incompatible responses explain the next action", async () => {
  const ui = await browser();
  assert.match(ui.run("readableError('Model HTTP 400: OVERAGE_REQUEST_LIMIT_EXCEEDED')"), /上游用量已达到限制/);
  assert.match(ui.run("readableError('Model response is missing choices[0].message')"), /不完整或不兼容/);
});
