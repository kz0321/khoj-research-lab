/* Khoj Research Lab: framework-free client. All server-provided text is rendered
 * with textContent/createTextNode; source text is never interpreted as HTML. */
"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const state = { collections: [], config: {}, runId: null, result: null, polling: null,
  timer: null, startedAt: null, isRunning: false, uploadBusy: false, toastTimer: null, historyExpanded: false, outcomes: new Map(),
  viewVersion: 0, cancelRequested: false };
const modeHelp = {
  verified: "检索资料后逐条检查结论；证据不足时，尝试补充检索。",
  multi_step: "允许多轮工具调用；候选结论不经过独立的证据检查。",
  single_rag: "先进行一次资料检索，再根据检索结果生成回答。",
  no_tools: "直接调用语言模型，不读取资料库；回答没有文档证据保障。",
  verified_no_repair: "检查候选结论的支持情况，发现缺口后不再追加检索。"
};
const statusLabels = { supported: "已支持", contradicted: "存在矛盾", insufficient: "证据不足",
  insufficiently_supported: "证据不足", unsupported: "证据不足", unchecked: "未检查", unverified: "未检查",
  queued: "排队中", running: "研究中", completed: "已完成", failed: "失败", cancelled: "已停止" };
const toolLabels = { semantic_search_files: "文档语义检索", view_file: "阅读文档", search_web: "网页搜索",
  read_webpage: "读取网页", verify: "检查证据", verification: "检查证据", plan: "规划研究",
  synthesis: "综合报告", draft: "起草结论", repair: "补充检索", search_documents: "文档检索",
  read_file: "阅读文档", web_search: "网页搜索", read_page: "读取网页" };

function el(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined && content !== null) node.textContent = String(content);
  return node;
}
function text(value) {
  if (value == null) return "";
  if (typeof value === "string") return value;
  try { return JSON.stringify(value); } catch (_) { return String(value); }
}
function readableError(value) {
  if (Array.isArray(value)) return value.map(v => v.msg || text(v)).join("；");
  if (value && typeof value === "object") return value.message || value.error || text(value);
  const message = String(value || "发生未知错误，请稍后重试。");
  if (/Configure LLM_API_KEY|LLM_API_KEY is not configured/i.test(message)) return "生成模型尚未配置。请在项目的 .env 文件中设置模型服务地址、模型名和 API 密钥，重启服务后再开始研究。";
  if (/OVERAGE_REQUEST_LIMIT_EXCEEDED|ServiceQuotaExceededException|reached the limit for overages/i.test(message)) return "模型服务的上游用量已达到限制。请在服务商控制台确认可用额度或联系服务商处理，再重新发起研究。\n" + message;
  if (/nonempty choices list|choices\[0\]\.message|streaming delta|message\.content must be nonempty/i.test(message)) return "模型服务返回了不完整或不兼容的响应，未生成有效报告。请检查该服务的非流式对话接口是否正常。\n" + message;
  if (/insufficient.?balance|HTTP 402/i.test(message)) return `模型服务账户余额不足，请补充额度或切换可用的模型配置后重试。\n${message}`;
  return message;
}
async function api(path, options = {}) {
  let response;
  try { response = await fetch(path, options); }
  catch (_) { throw new Error("无法连接本地服务。请确认项目已启动，然后重试。"); }
  const type = response.headers.get("content-type") || "";
  const body = type.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) throw new Error(readableError(body?.detail || body?.error || body || `HTTP ${response.status}`));
  return body;
}
function jsonPost(path, body) {
  return api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
}
function toast(message, error = false) {
  clearTimeout(state.toastTimer);
  const node = $("#toast");
  node.textContent = message; node.classList.toggle("error", error); node.hidden = false;
  state.toastTimer = setTimeout(() => { node.hidden = true; }, error ? 7500 : 4200);
}
function prettyDate(value) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "" : date.toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" });
}
function formatSeconds(value) {
  const seconds = Number(value || 0);
  return seconds >= 60 ? `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s` : `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
}
function normalizeStatus(value) {
  const normalized = String(value || "unchecked").toLowerCase().replace(/[ -]/g, "_");
  if (["insufficiently_supported", "unsupported", "insufficient_evidence"].includes(normalized)) return "insufficient";
  if (normalized === "unverified") return "unchecked";
  return normalized;
}
function saveCollection(id) { try { localStorage.setItem("khoj-research-collection", id); } catch (_) { /* Optional preference only. */ } }
function readCollection() { try { return localStorage.getItem("khoj-research-collection") || ""; } catch (_) { return ""; } }

async function loadStatus() {
  try {
    state.config = await api("/api/status");
    $("#model-name").textContent = state.config.model || "未配置模型";
    $("#model-caption").textContent = state.config.configured ? "模型已配置 · 文档存储在本机" : "请配置模型 API";
    $("#model-dot").className = `status-dot ${state.config.configured ? "ready" : "error"}`;
    renderConfig();
  } catch (error) {
    $("#model-name").textContent = "服务未连接";
    $("#model-caption").textContent = "请启动本地服务后刷新";
    $("#model-dot").className = "status-dot error";
    toast(error.message, true);
  }
}
function renderConfig() {
  const root = $("#config-body"); root.replaceChildren();
  const dl = el("dl", "config-grid");
  const items = [["生成模型", state.config.model || "未配置"], ["嵌入模型", state.config.embedding_model || "由服务端设置"],
    ["Khoj 版本", state.config.upstream_commit ? String(state.config.upstream_commit).slice(0, 12) : "见项目文档"]];
  const labels = { max_rounds: "决策轮次上限", max_iterations: "决策轮次上限", max_tool_calls: "工具调用上限",
    max_repair_rounds: "修复轮次上限", max_repairs: "修复轮次上限", max_seconds: "运行时限（秒）", timeout_seconds: "运行时限（秒）",
    decision_rounds: "决策轮次上限", tool_calls: "工具调用上限", repair_rounds: "修复轮次上限", elapsed_seconds: "运行时限（秒）",
    model_calls: "模型调用上限", retrieval_top_k: "单次检索片段数", max_claims: "候选结论上限", max_evidence: "证据片段上限", final_answer_tokens: "生成 tokens 上限" };
  for (const [key, value] of Object.entries(state.config.limits || {})) items.push([labels[key] || key, text(value)]);
  for (const [key, value] of items) dl.append(el("dt", "", key), el("dd", "", value));
  root.append(dl, el("p", "config-note", "文档与研究记录保存在本机。使用 API 模型时，问题和检索到的相关片段会发往所配置的模型服务。联网检索仅在开启后使用。"));
}
async function loadCollections(preferred) {
  const payload = await api("/api/collections");
  state.collections = Array.isArray(payload) ? payload : (payload.collections || []);
  const selected = preferred || $("#collection").value || readCollection();
  const select = $("#collection"); select.replaceChildren();
  if (!state.collections.length) select.append(new Option("尚无资料库 · 请创建或载入示例", ""));
  for (const collection of state.collections) select.append(new Option(collection.name || collection.id, collection.id));
  if (state.collections.some(c => c.id === selected)) select.value = selected;
  updateCollectionStats();
}
function updateCollectionStats() {
  const id = $("#collection").value;
  const current = state.collections.find(c => c.id === id);
  $("#collection-stats").textContent = current ? `${current.documents ?? current.document_count ?? 0} 份文档 · ${current.chunks ?? current.chunk_count ?? 0} 个证据片段` : "先创建资料库，再上传研究材料";
  if (id) saveCollection(id);
}
async function createCollection(event) {
  event.preventDefault();
  const input = $("#collection-name"); const name = input.value.trim();
  if (!name) return;
  const button = $("button[type=submit]", event.target); button.disabled = true;
  try {
    const result = await jsonPost("/api/collections", { name });
    await loadCollections(result.id || result.collection_id);
    $("#new-collection-dialog").close(); input.value = "";
    toast("资料库已创建，可以上传文档了。");
  } catch (error) { toast(error.message, true); }
  finally { button.disabled = false; }
}
async function uploadFiles(files) {
  if (!files?.length || state.uploadBusy) return;
  const collectionId = $("#collection").value;
  if (!collectionId) { toast("请先创建资料库，或载入示例资料库。", true); return; }
  if (files.length > 20) { toast("每批最多上传 20 份文档，请分批上传。", true); return; }
  if ([...files].some(file => file.size > 10_000_000)) { toast("每份文档不能超过 10 MB，请缩小文件后重试。", true); return; }
  const unsupported = [...files].filter(file => !/\.(pdf|docx|md|markdown|html|htm|txt)$/i.test(file.name));
  if (unsupported.length) { toast("目前支持 PDF、Word (.docx)、Markdown、HTML 和 TXT 文档。", true); return; }
  state.uploadBusy = true;
  $("#drop-zone").setAttribute("aria-disabled", "true");
  $("#upload-label").textContent = `正在处理 ${files.length} 份文档…`;
  const form = new FormData(); for (const file of files) form.append("files", file);
  try {
    const result = await api(`/api/collections/${encodeURIComponent(collectionId)}/documents`, { method: "POST", body: form });
    await loadCollections(collectionId);
    if (Array.isArray(result.errors) && result.errors.length) toast(`部分文档未能导入：${result.errors.map(readableError).join("；")}`, true);
    else toast("文档已导入并建立索引。");
  } catch (error) { toast(error.message, true); }
  finally {
    state.uploadBusy = false; $("#drop-zone").removeAttribute("aria-disabled");
    $("#upload-label").textContent = "拖入文档，或点击上传"; $("#file-input").value = "";
  }
}
async function loadDemo() {
  const button = $("#load-demo"); button.disabled = true; button.textContent = "正在准备示例资料…";
  try {
    const result = await jsonPost("/api/demo", {});
    await loadCollections(result.collection_id || result.id);
    if (result.question) setQuestion(result.question);
    else if (!$("#question").value.trim()) setQuestion($(".prompt-chip").dataset.prompt);
    toast("示例资料已载入。你可以直接开始研究。");
  } catch (error) { toast(error.message, true); }
  finally { button.disabled = false; button.textContent = "↗ 载入示例资料库"; }
}
function setQuestion(value) { $("#question").value = value; updateQuestionCount(); }
function updateQuestionCount() { $("#question-count").textContent = `${$("#question").value.length} / 3000`; }
function beginRunView(id = null) {
  state.viewVersion += 1;
  state.runId = id;
  state.cancelRequested = false;
  clearTimeout(state.polling); clearInterval(state.timer);
  return state.viewVersion;
}
function setRunning(running) {
  state.isRunning = running;
  $("#run-button").disabled = running;
  $("#run-button span").textContent = running ? "研究进行中" : "开始研究";
  $("#cancel-run").hidden = !running; $("#cancel-run").disabled = !state.runId || state.cancelRequested;
  $("#mode").disabled = running; $("#allow-web").disabled = running;
  $("#collection").disabled = running;
  $("#progress-spinner").hidden = !running;
  if (!running) { clearTimeout(state.polling); clearInterval(state.timer); }
}
function resetResults() {
  state.result = null;
  $("#report-empty").hidden = false; $("#report-content").hidden = true;
  $("#report-content").replaceChildren(); $("#summary-metrics").hidden = true;
  $("#evidence-content").replaceChildren(el("p", "panel-empty", "正在收集材料。完成后可检查逐条结论及其证据。"));
  $("#trace-content").replaceChildren(el("p", "panel-empty", "等待工具调用记录…"));
  $("#evidence-count").textContent = "0"; $("#trace-count").textContent = "0";
  $("#export-md").disabled = true; $("#export-json").disabled = true;
  $("#error-panel").hidden = true;
  $("#progress-panel").classList.remove("is-incomplete");
}
async function startResearch(event) {
  event.preventDefault();
  if (state.isRunning) return;
  const question = $("#question").value.trim(); if (!question) return;
  const mode = $("#mode").value; const collectionId = $("#collection").value;
  if (mode !== "no_tools" && !collectionId) { toast("请选择资料库，或先载入示例资料。", true); return; }
  if (state.uploadBusy) { toast("文档还在建立索引，请稍后再开始。", true); return; }
  const version = beginRunView();
  resetResults(); selectTab("report"); setRunning(true);
  $("#progress-panel").hidden = false;
  $("#progress-title").textContent = "正在准备研究";
  $("#progress-message").textContent = "正在提交请求…";
  setStage("plan"); state.startedAt = Date.now(); startTimer();
  try {
    const payload = await jsonPost("/api/research", { question, collection_id: collectionId || "demo",
      mode, allow_web: $("#allow-web").checked });
    if (version !== state.viewVersion) return;
    state.runId = payload.id || payload.run_id;
    if (!state.runId) throw new Error("服务未返回研究任务编号。");
    $("#cancel-run").disabled = false;
    history.replaceState(null, "", `?run=${encodeURIComponent(state.runId)}`);
    await loadHistory();
    if (version === state.viewVersion) await pollRun(0, version);
  } catch (error) {
    if (version !== state.viewVersion) return;
    showError(error.message); setRunning(false);
    $("#progress-title").textContent = "研究未能启动";
    $("#progress-message").textContent = "请处理下方提示后重新提交。";
  }
}
function startTimer() {
  clearInterval(state.timer);
  const tick = () => { $("#elapsed").textContent = formatSeconds((Date.now() - state.startedAt) / 1000); };
  tick(); state.timer = setInterval(tick, 1000);
}
function setStage(stage) {
  const stages = ["plan", "search", "verify", "done"];
  const index = stages.indexOf(stage);
  $$(".progress-track>span").forEach(node => node.classList.toggle("active", stages.indexOf(node.dataset.stage) <= index));
}
function updateProgress(run) {
  const progress = run.progress || [];
  const latest = Array.isArray(progress) ? progress.at(-1) : progress;
  let message = latest ? (typeof latest === "string" ? latest : latest.message || latest.detail || latest.stage || text(latest)) : "Agent 正在处理问题，请稍候…";
  $("#progress-message").textContent = message;
  const stageText = `${typeof latest === "object" ? latest?.stage || "" : ""} ${message}`.toLowerCase();
  if (/verif|check|repair|核|检查|修复/.test(stageText)) { setStage("verify"); $("#progress-title").textContent = "正在核对结论与证据"; }
  else if (/synth|report|final|报告|综合/.test(stageText)) { setStage("done"); $("#progress-title").textContent = "正在整理研究报告"; }
  else if (/search|retriev|tool|检索|文档|工具/.test(stageText)) { setStage("search"); $("#progress-title").textContent = "正在检索与阅读资料"; }
  else { $("#progress-title").textContent = run.status === "queued" ? "任务已提交，等待开始" : "正在研究问题"; }
  if (Array.isArray(run.trace)) renderTrace(run.trace);
}
async function pollRun(failures = 0, version = state.viewVersion) {
  if (version !== state.viewVersion) return;
  const targetId = state.runId;
  if (!targetId) return;
  try {
    const run = await api(`/api/runs/${encodeURIComponent(targetId)}`);
    if (version !== state.viewVersion || targetId !== state.runId) return;
    updateProgress(run);
    if (run.status === "completed") {
      setRunning(false); state.result = run.result || run; renderResult(state.result, run.status);
      showCompletedOutcome(run);
      $("#elapsed").textContent = formatSeconds(state.result.elapsed_seconds || ((Date.now() - state.startedAt) / 1000));
      setStage("done"); await loadHistory();
    } else if (["failed", "cancelled"].includes(run.status)) {
      setRunning(false);
      $("#progress-title").textContent = run.status === "cancelled" ? "研究已停止" : "研究未能完成";
      $("#progress-message").textContent = run.status === "cancelled" ? "任务已停止，可以调整问题后再次发起研究。" : "请查看下方错误信息，调整配置后重试。";
      if (run.result) { state.result = run.result; renderResult(run.result, run.status); }
      if (run.status === "failed") showError(readableError(run.error));
      await loadHistory();
    } else {
      state.polling = setTimeout(() => pollRun(0, version), 1500);
    }
  } catch (error) {
    if (version !== state.viewVersion || targetId !== state.runId) return;
    if (failures < 3) {
      $("#progress-message").textContent = "连接暂时中断，正在重新连接…";
      state.polling = setTimeout(() => pollRun(failures + 1, version), 2500);
    } else { setRunning(false); showError(`${error.message} 任务可能仍在服务端运行，可从最近的研究重新打开。`); }
  }
}
async function cancelResearch() {
  if (!state.runId || state.cancelRequested) return;
  const targetId = state.runId, version = state.viewVersion;
  state.cancelRequested = true;
  $("#cancel-run").disabled = true;
  try {
    await jsonPost(`/api/runs/${encodeURIComponent(targetId)}/cancel`, {});
    if (version === state.viewVersion && state.isRunning) $("#progress-message").textContent = "停止请求已发送，等待当前操作退出…";
  } catch (error) {
    if (version !== state.viewVersion) return;
    state.cancelRequested = false; toast(error.message, true); $("#cancel-run").disabled = false;
  }
}
function showError(message) {
  $("#error-panel").hidden = false; $("#error-message").textContent = message;
}
function showCompletedOutcome(run) {
  const outcome = ResearchOutcomes.classifyRun(run);
  state.outcomes.set(run.id, outcome);
  $("#progress-title").textContent = outcome.title || outcome.label;
  $("#progress-message").textContent = outcome.message || "本次运行已结束，可以查看保存的记录。";
  $("#progress-panel").classList.toggle("is-incomplete", ["insufficient", "no_answer"].includes(outcome.kind));
}

function evidenceById(id) { return (state.result?.evidence || []).find(item => String(item.id) === String(id)); }
function appendInline(parent, value) {
  const source = text(value);
  // Small, deliberately non-HTML renderer: bold, inline code, and evidence IDs.
  const expression = /(\*\*[^*\n]+\*\*|`[^`\n]+`|\[(?:E\d+)(?:\s*[,;]\s*E\d+)*\])/g;
  let cursor = 0;
  for (const match of source.matchAll(expression)) {
    parent.append(document.createTextNode(source.slice(cursor, match.index)));
    const token = match[0];
    if (token.startsWith("**")) parent.append(el("strong", "", token.slice(2, -2)));
    else if (token.startsWith("`")) parent.append(el("code", "", token.slice(1, -1)));
    else {
      for (const id of token.slice(1, -1).split(/\s*[,;]\s*/)) {
        const citation = el("button", "citation-button", `[${id}]`); citation.type = "button";
        citation.setAttribute("aria-label", `查看证据 ${id}`); citation.addEventListener("click", () => openEvidence(id));
        parent.append(citation);
      }
    }
    cursor = match.index + token.length;
  }
  parent.append(document.createTextNode(source.slice(cursor)));
}
function renderMarkdown(root, value) {
  const lines = text(value).replace(/\r\n/g, "\n").split("\n");
  let paragraph = []; let list = null;
  const flush = () => { if (paragraph.length) { const p = el("p"); appendInline(p, paragraph.join(" ")); root.append(p); paragraph = []; } };
  for (const line of lines) {
    if (!line.trim()) { flush(); list = null; continue; }
    const heading = line.match(/^(#{1,6})\s+(.+)/);
    const item = line.match(/^\s*(?:([-*])|\d+[.)])\s+(.+)/);
    if (heading) { flush(); list = null; const h = el(heading[1].length <= 1 ? "h2" : "h3"); appendInline(h, heading[2]); root.append(h); }
    else if (item) { flush(); const tag = item[1] ? "ul" : "ol"; if (!list || list.tagName.toLowerCase() !== tag) { list = el(tag); root.append(list); } const li = el("li"); appendInline(li, item[2]); list.append(li); }
    else if (/^>\s?/.test(line)) { flush(); list = null; const quote = el("blockquote"); appendInline(quote, line.replace(/^>\s?/, "")); root.append(quote); }
    else if (/^[-*_]{3,}\s*$/.test(line)) { flush(); list = null; }
    else { if (list) list = null; paragraph.push(line); }
  }
  flush();
}
function renderResult(result, runStatus = "completed") {
  $("#report-empty").hidden = true; $("#report-content").hidden = false;
  $("#export-md").disabled = false; $("#export-json").disabled = false;
  renderMetrics(result); renderReport(result, runStatus); renderEvidence(result); renderTrace(result.trace || []);
}
function renderMetrics(result) {
  const root = $("#summary-metrics"); root.hidden = false; root.replaceChildren();
  const claims = result.claims || []; const supported = claims.filter(c => normalizeStatus(c.status) === "supported").length;
  const usage = result.usage || {}; const tokens = Number(usage.input_tokens || 0) + Number(usage.output_tokens || 0);
  const tokenLabel = usage.unknown_usage_attempts ? "已知 tokens · 含用量未知的失败请求" : "输入 + 输出 tokens";
  const metrics = [[claims.length ? `${supported} / ${claims.length}` : "—", claims.length ? "检查器判为支持" : "暂无候选结论"], [(result.evidence || []).length, "已收集证据"],
    [result.tool_calls ?? (result.trace || []).filter(t => t.tool).length, "工具调用"], [tokens.toLocaleString(), tokenLabel],
    [formatSeconds(result.elapsed_seconds), "总耗时"]];
  for (const [value, label] of metrics) { const box = el("div", "metric"); box.append(el("strong", "", value), el("small", "", label)); root.append(box); }
}
function renderReport(result, runStatus = "completed") {
  const root = $("#report-content"); root.replaceChildren();
  const outcome = ResearchOutcomes.classifyRun({ status: runStatus, result });
  if (["insufficient", "no_answer"].includes(outcome.kind)) {
    const box = el("section", "no-answer-box");
    box.append(el("h2", "", outcome.title), el("p", "", outcome.message));
    if (outcome.kind === "insufficient") {
      const diagnosis = ResearchOutcomes.diagnose(result);
      const reasons = el("ul", "outcome-reasons");
      for (const reason of diagnosis.reasons) {
        const item = el("li"); item.append(el("strong", "", `${reason.label}：`), document.createTextNode(reason.text)); reasons.append(item);
      }
      box.append(reasons, el("h3", "", "可以这样继续"));
      const steps = el("ol", "outcome-next");
      for (const suggestion of diagnosis.nextSteps) steps.append(el("li", "", suggestion));
      box.append(steps);
    }
    const actions = el("div", "outcome-actions");
    const refine = el("button", "secondary-button", "补充问题"); refine.type = "button";
    refine.addEventListener("click", () => { $("#question").scrollIntoView({ block: "center" }); $("#question").focus(); });
    const inspect = el("button", "text-button", "查看检索记录 →"); inspect.type = "button";
    inspect.addEventListener("click", () => selectTab("trace", true));
    actions.append(refine, inspect); box.append(actions); root.append(box);
  }
  if (result.answer) {
    const answer = el("div", "report-answer"); answer.append(el("p", "section-kicker", "ANSWER / 简要回答"));
    const answerClaim = (result.claims || []).find(claim => claim.id === "A0");
    const citations = (answerClaim?.evidence_ids || []).map(id => `[${id}]`).join(" ");
    renderMarkdown(answer, `${result.answer}${citations ? " " + citations : ""}`); root.append(answer);
  }
  if (result.report) {
    let displayedReport = result.report;
    // The downloadable report includes a full evidence appendix. The interface
    // keeps original passages in the inspectable ledger and avoids repeating
    // the same answer and unresolved list twice.
    if (displayedReport.startsWith("# Research report\n")) {
      const findingsStart = displayedReport.search(/^## (Supported findings|Findings \(not verified\))\s*$/m);
      if (findingsStart >= 0) displayedReport = displayedReport.slice(findingsStart);
      displayedReport = displayedReport.split(/^## Evidence\s*$/m)[0];
      if ((result.unresolved || []).length) displayedReport = displayedReport.split(/^## Unresolved questions\s*$/m)[0];
      if (!(result.claims || []).length) displayedReport = displayedReport.replace(/^## (Supported findings|Findings \(not verified\))\s*$/gm, "");
    }
    renderMarkdown(root, displayedReport);
  }
  else if (!result.answer) root.append(el("p", "", "本次研究没有生成可支持的结论。请查看证据台账和未解决的问题。"));
  const unresolved = result.unresolved || [];
  if (unresolved.length) {
    const box = el("section", "unresolved-box"); box.append(el("h3", "", "仍需确认的问题")); const list = el("ul");
    for (const item of unresolved) { const li = el("li"); appendInline(li, typeof item === "string" ? item : item.question || item.reason || item.text || text(item)); list.append(li); }
    box.append(list); root.append(box);
  }
  if (result.stop_reason) root.append(el("p", "stop-note", `停止原因：${result.stop_reason}`));
  if ((result.evidence || []).length) {
    const inspect = el("button", "text-button", `查看 ${result.evidence.length} 条原始证据与检查记录 →`);
    inspect.type = "button"; inspect.addEventListener("click", () => selectTab("evidence", true)); root.append(inspect);
  }
}
function renderEvidence(result) {
  const root = $("#evidence-content"); root.replaceChildren();
  const claims = result.claims || [], evidence = result.evidence || [];
  $("#evidence-count").textContent = evidence.length;
  root.append(el("p", "evidence-intro", "检查状态来自规则校验与模型判断，并非人工标注的真值。点击引用，查看保留的原始文本与来源位置。"));
  if (!claims.length) root.append(el("p", "panel-empty", result.mode === "no_tools"
    ? "本次使用无工具模式，没有文档证据和候选结论记录。"
    : "本次没有形成候选结论。取回的片段仍保留在下方，可核对它们是否覆盖问题。"));
  claims.forEach((claim, index) => {
    const card = el("article", "claim-card"); const top = el("div", "claim-top");
    top.append(el("span", "claim-id", claim.id || `C${index + 1}`));
    const statement = el("p"); appendInline(statement, claim.text || claim.claim || ""); top.append(statement);
    const status = normalizeStatus(claim.status);
    top.append(el("span", `verification-badge ${status}`, statusLabels[status] || status)); card.append(top);
    if (claim.reason) card.append(el("p", "claim-reason", claim.reason));
    const ids = claim.evidence_ids || claim.citations || [];
    if (ids.length) {
      const sources = el("div", "claim-sources");
      for (const rawId of ids) {
        const id = typeof rawId === "object" ? rawId.evidence_id || rawId.id : rawId;
        const evidenceItem = evidenceById(id); const button = el("button", "source-chip"); button.type = "button";
        button.append(el("strong", "", id), el("span", "", evidenceItem?.title || evidenceItem?.source_id || "查看引用"));
        button.addEventListener("click", () => openEvidence(id)); sources.append(button);
      }
      card.append(sources);
    }
    root.append(card);
  });
  if (evidence.length) {
    root.append(el("h3", "sources-heading", `收集到的证据 · ${evidence.length}`));
    for (const item of evidence) {
      const row = el("button", "source-row"); row.type = "button";
      const label = el("span"); label.append(el("strong", "", `[${item.id}] ${item.title || item.source_id || "来源文档"}`), el("small", "", locationText(item.location)));
      row.append(label, el("span", "", "查看原文 ↗")); row.addEventListener("click", () => openEvidence(item.id)); root.append(row);
    }
  }
}
function locationText(location) {
  if (typeof location === "string") return location;
  if (location && typeof location === "object") return Object.entries(location).map(([key, value]) => `${key}: ${text(value)}`).join(" · ");
  return "位置详见来源记录";
}
function openEvidence(id) {
  const item = evidenceById(id);
  if (!item) { toast(`记录中未找到证据 ${id}，这条引用可能无效。`, true); return; }
  $("#evidence-dialog-title").textContent = `证据 ${item.id}`;
  const body = $("#evidence-dialog-body"); body.replaceChildren(); const meta = el("dl", "evidence-meta");
  const rows = [["来源", item.title || item.source_id || ""], ["来源编号", item.source_id || ""], ["位置", locationText(item.location)]];
  if (item.retrieved_at) rows.push(["获取时间", item.retrieved_at]);
  for (const [label, value] of rows) if (value) meta.append(el("dt", "", label), el("dd", "", value));
  body.append(meta, el("blockquote", "evidence-quote", item.text || item.passage || "该记录没有保存原始文本。"));
  if (item.url) {
    try {
      const url = new URL(item.url);
      if (["http:", "https:"].includes(url.protocol)) {
        const link = el("a", "source-link", "打开来源网页 ↗"); link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer"; body.append(link);
      }
    } catch (_) { /* Non-web source locations are displayed as text only. */ }
  }
  $("#evidence-dialog").showModal();
}
function renderTrace(trace) {
  const root = $("#trace-content"); root.replaceChildren(); $("#trace-count").textContent = trace.length;
  if (!trace.length) { root.append(el("p", "panel-empty", "本次记录尚无工具调用。")); return; }
  root.append(el("p", "evidence-intro", "行动日志记录工具及其参数、状态与耗时。展开条目可查看细节；日志不包含模型的私有推理过程。"));
  trace.forEach((entry, index) => {
    const row = el("div", "trace-row"); row.append(el("span", "trace-step", entry.step ?? index + 1));
    const details = el("details"), summary = el("summary");
    const name = entry.tool || entry.stage || entry.action || "action";
    summary.append(el("strong", "", toolLabels[name] || name), el("span", "", entry.status || "记录")); details.append(summary);
    const values = { tool: name, ...(entry.args ? { arguments: entry.args } : {}), ...(entry.evidence_ids ? { evidence_ids: entry.evidence_ids } : {}),
      ...(entry.result_count != null ? { result_count: entry.result_count } : {}),
      ...(entry.search_provider ? { search_provider: entry.search_provider, search_scope: entry.search_scope } : {}),
      ...(entry.search_attempts ? { search_attempts: entry.search_attempts } : {}),
      ...(entry.attempt != null ? { attempt: entry.attempt } : {}), ...(entry.result ? { result: entry.result } : {}), ...(entry.observation ? { observation: entry.observation } : {}), ...(entry.message ? { message: entry.message } : {}) };
    details.append(el("pre", "", JSON.stringify(values, null, 2)));
    if (entry.error) details.append(el("p", "trace-error", readableError(entry.error)));
    row.append(details, el("span", "trace-duration", entry.elapsed_ms != null ? formatSeconds(entry.elapsed_ms / 1000) : "")); root.append(row);
  });
}
function selectTab(name, focus = false) {
  $$(".result-tabs button").forEach(button => {
    const selected = button.dataset.tab === name;
    button.setAttribute("aria-selected", String(selected)); button.tabIndex = selected ? 0 : -1;
    $(`#panel-${button.dataset.tab}`).hidden = !selected;
    if (selected && focus) button.focus();
  });
}
async function exportRun(format) {
  if (!state.runId) return;
  const targetId = state.runId, version = state.viewVersion;
  const button = $(`#export-${format}`); button.disabled = true;
  try {
    const response = await fetch(`/api/runs/${encodeURIComponent(targetId)}/export?format=${encodeURIComponent(format)}`);
    if (!response.ok) throw new Error(`导出失败（HTTP ${response.status}）。`);
    const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = el("a");
    link.href = url; link.download = `research-${targetId}.${format}`; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { toast(error.message, true); }
  finally { if (version === state.viewVersion) button.disabled = false; }
}
async function loadHistory() {
  try {
    const payload = await api("/api/runs"); const runs = Array.isArray(payload) ? payload : payload.runs || [];
    const root = $("#history"); root.replaceChildren();
    if (!runs.length) { root.append(el("p", "sidebar-empty", "完成一次研究后，记录会显示在这里。")); return; }
    for (const run of (state.historyExpanded ? runs : runs.slice(0, 8))) {
      const button = el("button", `history-item${run.id === state.runId ? " selected" : ""}`); button.type = "button";
      button.dataset.runId = run.id;
      const outcome = state.outcomes.get(run.id) || ResearchOutcomes.classifyRun(run);
      const incomplete = ["insufficient", "no_answer"].includes(outcome.kind);
      button.append(el("span", `history-marker${incomplete ? " is-incomplete" : ""}`, incomplete ? "!" : run.status === "completed" ? "▤" : run.status === "running" ? "◷" : "·"));
      const label = el("span"); label.append(el("strong", "", run.question || "研究任务"), el("small", "", `${outcome.label} · ${prettyDate(run.created_at)}`));
      button.append(label); button.addEventListener("click", () => openRun(run.id)); root.append(button);
    }
    if (runs.length > 8) {
      const expand = el("button", "text-button", state.historyExpanded ? "收起历史记录" : `查看全部 ${runs.length} 条记录`);
      expand.type = "button"; expand.addEventListener("click", () => { state.historyExpanded = !state.historyExpanded; loadHistory(); });
      root.append(expand);
    }
  } catch (_) { /* History is optional; primary workflow reports connection errors. */ }
}
async function openRun(id) {
  if (state.isRunning && id !== state.runId) { toast("请等待或停止当前研究，再打开其他记录。"); return; }
  if (state.isRunning && id === state.runId) return;
  const version = beginRunView(id);
  resetResults();
  $("#progress-panel").hidden = false;
  $("#progress-title").textContent = "正在载入研究记录";
  $("#progress-message").textContent = "正在读取保存的结果…";
  try {
    const run = await api(`/api/runs/${encodeURIComponent(id)}`);
    if (version !== state.viewVersion) return;
    selectTab("report");
    history.replaceState(null, "", `?run=${encodeURIComponent(id)}`);
    if (run.question) setQuestion(run.question);
    if (run.mode && modeHelp[run.mode]) { $("#mode").value = run.mode; $("#mode-help").textContent = modeHelp[run.mode]; }
    if (run.collection_id && state.collections.some(c => c.id === run.collection_id)) { $("#collection").value = run.collection_id; updateCollectionStats(); }
    const allowWeb = run.allow_web ?? run.request?.allow_web;
    if (typeof allowWeb === "boolean") $("#allow-web").checked = allowWeb;
    state.startedAt = run.created_at ? Date.parse(run.created_at) : Date.now();
    if (!Number.isFinite(state.startedAt)) state.startedAt = Date.now();
    $("#progress-panel").hidden = false;
    if (["queued", "running"].includes(run.status)) { setRunning(true); startTimer(); await pollRun(0, version); }
    else {
      setRunning(false);
      if (run.result) { state.result = run.result; renderResult(run.result, run.status); }
      else if (run.trace) renderTrace(run.trace);
      $("#progress-title").textContent = statusLabels[run.status] || run.status;
      $("#progress-message").textContent = run.status === "completed" ? "已载入保存的研究记录。" : "已载入历史任务。";
      $("#elapsed").textContent = run.result?.elapsed_seconds ? formatSeconds(run.result.elapsed_seconds) : "";
      if (run.status === "completed") { showCompletedOutcome(run); setStage("done"); }
      if (run.status === "failed") showError(readableError(run.error));
    }
    await loadHistory();
  } catch (error) { if (version === state.viewVersion) toast(error.message, true); }
}

$("#research-form").addEventListener("submit", startResearch);
$("#question").addEventListener("input", updateQuestionCount);
$("#question").addEventListener("keydown", event => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); $("#research-form").requestSubmit(); } });
$("#mode").addEventListener("change", () => { $("#mode-help").textContent = modeHelp[$("#mode").value]; });
$("#collection").addEventListener("change", updateCollectionStats);
$("#new-collection").addEventListener("click", () => { $("#new-collection-dialog").showModal(); $("#collection-name").focus(); });
$("#collection-form").addEventListener("submit", createCollection);
$("#load-demo").addEventListener("click", loadDemo);
$("#file-input").addEventListener("change", event => uploadFiles(event.target.files));
$("#drop-zone").addEventListener("keydown", event => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); $("#file-input").click(); } });
for (const type of ["dragenter", "dragover"]) $("#drop-zone").addEventListener(type, event => { event.preventDefault(); $("#drop-zone").classList.add("drag-over"); });
for (const type of ["dragleave", "drop"]) $("#drop-zone").addEventListener(type, event => { event.preventDefault(); $("#drop-zone").classList.remove("drag-over"); });
$("#drop-zone").addEventListener("drop", event => uploadFiles(event.dataTransfer.files));
$("#cancel-run").addEventListener("click", cancelResearch);
$("#model-info").addEventListener("click", () => $("#config-dialog").showModal());
$("#refresh-history").addEventListener("click", loadHistory);
$("#export-md").addEventListener("click", () => exportRun("md"));
$("#export-json").addEventListener("click", () => exportRun("json"));
$$(".prompt-chip").forEach(button => button.addEventListener("click", () => { setQuestion(button.dataset.prompt); $("#question").focus(); }));
$$(".close-dialog").forEach(button => button.addEventListener("click", () => button.closest("dialog").close()));
$$("dialog").forEach(dialog => dialog.addEventListener("click", event => { if (event.target === dialog) { const box = dialog.getBoundingClientRect(); if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close(); } }));
$$(".result-tabs button").forEach(button => button.addEventListener("click", () => selectTab(button.dataset.tab)));
$(".result-tabs").addEventListener("keydown", event => {
  const tabs = $$(".result-tabs button"); const current = tabs.findIndex(tab => tab.getAttribute("aria-selected") === "true");
  let next = current;
  if (event.key === "ArrowRight") next = (current + 1) % tabs.length;
  else if (event.key === "ArrowLeft") next = (current + tabs.length - 1) % tabs.length;
  else if (event.key === "Home") next = 0;
  else if (event.key === "End") next = tabs.length - 1;
  else return;
  event.preventDefault(); selectTab(tabs[next].dataset.tab, true);
});
window.addEventListener("beforeunload", () => { clearTimeout(state.polling); clearInterval(state.timer); });
Promise.allSettled([loadStatus(), loadCollections().catch(error => toast(error.message, true)), loadHistory()]).then(() => {
  const runId = new URLSearchParams(location.search).get("run");
  if (runId && /^[a-f0-9]{32}$/i.test(runId)) openRun(runId);
});
