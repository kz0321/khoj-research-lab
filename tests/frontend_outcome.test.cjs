"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { classifyRun, diagnose } = require("../app/static/outcome.js");

const missing = {
  mode: "verified", answer: "", claims: [], unresolved: ["The indexed demo documents do not mention the requested topic."],
  configuration: { allow_web: true },
  trace: [
    { tool: "semantic_search_files", status: "completed", evidence_ids: ["E1", "E2", "E3", "E4", "E5"], result_count: 5 },
    ...Array.from({ length: 3 }, () => ({ tool: "search_web", status: "failed", error: "No results found." })),
  ],
};

test("completed empty result is evidence insufficient, not successful answering", () => {
  const outcome = classifyRun({ status: "completed", result: missing });
  assert.equal(outcome.kind, "insufficient");
  assert.equal(outcome.title, "未找到足够证据");
  assert.equal(outcome.label, "证据不足");
});
test("real failure pattern distinguishes web no-results from retrieved but insufficient local passages", () => {
  const details = diagnose(missing);
  assert.equal(details.reasons.length, 2);
  assert.match(details.reasons[0].text, /3 次联网搜索未返回结果/);
  assert.match(details.reasons[0].text, /不能证明相关研究不存在/);
  assert.match(details.reasons[1].text, /取回了 5 条片段/);
  assert.doesNotMatch(details.reasons[1].text, /工具失败/);
  assert.ok(details.nextSteps.some(value => /全称、研究领域/.test(value)));
});
test("list rows without result details remain neutral", () => {
  assert.equal(classifyRun({ status: "completed" }).label, "运行结束");
});
test("failed or cancelled tasks are not relabeled as evidence abstentions", () => {
  assert.equal(classifyRun({ status: "failed", result: missing }).kind, "failed");
  assert.equal(classifyRun({ status: "cancelled", result: missing }).kind, "cancelled");
});
test("an answer is presented as generated, never certified correct", () => {
  assert.equal(classifyRun({ status: "completed", result: { answer: "A supported response." } }).label, "已生成回答");
});
test("partial supported findings can coexist with an incomplete answer", () => {
  const outcome = classifyRun({ status: "completed", result: { ...missing, claims: [{ id: "C1", status: "supported" }] } });
  assert.equal(outcome.kind, "insufficient");
  assert.equal(outcome.label, "部分结论");
  assert.match(outcome.message, /局部发现仍保留/);
});
test("an earlier failed web attempt does not erase a later successful one", () => {
  const details = diagnose({ ...missing, trace: [...missing.trace, { tool: "search_web", status: "completed", result_count: 3 }] });
  assert.match(details.reasons[0].text, /部分联网调用/);
  assert.doesNotMatch(details.reasons[0].text, /本次联网尝试没有提供可用信息/);
});
test("offline no-results and no-tools empty outputs remain distinct", () => {
  const details = diagnose({ ...missing, configuration: { allow_web: false }, trace: [{ tool: "semantic_search_files", status: "completed", result_count: 0, evidence_ids: [] }] });
  assert.match(details.reasons[0].text, /关闭了联网/);
  assert.match(details.reasons[1].text, /未取得可用片段/);
  assert.equal(classifyRun({ status: "completed", result: { ...missing, mode: "no_tools" } }).kind, "no_answer");
});
