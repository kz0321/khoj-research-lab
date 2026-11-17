/* Presentation-only outcome helpers. These never change saved model output or
 * infer that a failed search proves the absence of related work. */
(function (root, factory) {
  "use strict";
  const helpers = factory();
  if (typeof module === "object" && module.exports) module.exports = helpers;
  else root.ResearchOutcomes = helpers;
})(globalThis, function () {
  "use strict";
  const webTools = new Set(["search_web", "web_search", "read_webpage", "read_page"]);
  const localTools = new Set(["semantic_search_files", "search_documents", "view_file", "read_file"]);
  const isFailure = entry => ["failed", "error", "timeout"].includes(entry.status);

  function classifyRun(run) {
    if (run.status !== "completed") return { kind: run.status, label: { failed: "运行失败", cancelled: "已停止", running: "研究中", queued: "排队中" }[run.status] || run.status };
    // List endpoints do not include result details. "Ended" is deliberately
    // neutral until the stored result has actually been read.
    if (!run.result) return { kind: "ended", label: "运行结束" };
    const result = run.result;
    if (typeof result.answer === "string" && result.answer.trim()) {
      return { kind: "answered", label: "已生成回答", title: "研究已结束 · 已生成回答",
        message: "回答与证据台账已保存。请检查引用是否真正支持结论。" };
    }
    if ((result.mode || run.mode) === "no_tools") {
      return { kind: "no_answer", label: "未生成回答", title: "本次未生成可用回答",
        message: "模型调用已结束，但没有返回回答。可补充问题细节，并查看本次记录。" };
    }
    const hasPartialFindings = (result.claims || []).some(claim => claim.status === "supported");
    return { kind: "insufficient", label: hasPartialFindings ? "部分结论" : "证据不足",
      title: hasPartialFindings ? "已获得部分有依据的结论" : "未找到足够证据",
      message: hasPartialFindings
        ? "本次运行已结束，现有证据不足以形成完整回答；可支持的局部发现仍保留在下方。"
        : "本次运行已结束，但现有证据不足以形成回答。系统保留了检索记录和信息缺口，没有据此编造结论。" };
  }

  function diagnose(result) {
    const trace = Array.isArray(result.trace) ? result.trace : [];
    const web = trace.filter(entry => webTools.has(entry.tool));
    const local = trace.filter(entry => localTools.has(entry.tool));
    const webFailures = web.filter(isFailure);
    const noResults = webFailures.filter(entry => /no results found/i.test(String(entry.error || "")));
    const localIds = new Set(local.filter(entry => entry.status === "completed").flatMap(entry => entry.evidence_ids || []));
    const localReturned = localIds.size > 0 || local.some(entry => entry.status === "completed" && Number(entry.result_count) > 0);
    const reasons = [];
    if (webFailures.length) {
      const parts = [];
      if (noResults.length) parts.push(`${noResults.length} 次联网搜索未返回结果`);
      if (webFailures.length > noResults.length) parts.push(`${webFailures.length - noResults.length} 次联网工具调用失败`);
      const allFailed = web.length === webFailures.length;
      reasons.push({ label: "联网检索", text: `${parts.join("，")}。${allFailed ? "本次联网尝试没有提供可用信息；" : "部分联网调用没有取得信息；"}这不能证明相关研究不存在，具体错误可在行动轨迹中查看。` });
    } else if (result.configuration?.allow_web === false) {
      reasons.push({ label: "联网检索", text: "本次关闭了联网检索，研究范围仅限所选资料库。" });
    }
    if (localReturned) {
      reasons.push({ label: "本地资料", text: `${localIds.size ? `资料库检索取回了 ${localIds.size} 条片段` : "资料库检索取回了片段"}，但取回片段不等于覆盖了问题；现有证据仍不足以支持完整回答。请核对下方信息缺口与原文。` });
    } else if (local.length) {
      reasons.push({ label: "本地资料", text: local.some(isFailure)
        ? "本地检索记录包含工具失败，未取得可用片段。请查看行动轨迹并确认文档已经成功导入。"
        : "本次本地检索未取得可用片段。可检查所选资料库是否包含该主题的材料。" });
    }
    if (!reasons.length) reasons.push({ label: "证据情况", text: "现有记录未提供足够依据来形成完整回答。具体缺口请查看下方未解决问题和证据台账。" });
    const nextSteps = ["如果问题含缩写，请补充全称、研究领域和具体目标，帮助系统区分同名概念。",
      "选择覆盖该主题的资料库，或上传相关论文、项目说明和笔记后重新研究。"];
    if (webFailures.length) nextSteps.push("联网未取得可用信息时，可先补充可靠来源材料；待检索恢复后再重新运行。");
    else if (result.configuration?.allow_web === false) nextSteps.push("需要公开网页资料时，可以开启联网检索后重新研究。");
    return { reasons, nextSteps };
  }

  return Object.freeze({ classifyRun, diagnose });
});
