"""Insert measured results only after the complete held-out matrix passes audit."""
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parent.parent
RESULTS=ROOT/'eval/results/hotpot-test-frozen-r1'
NAMES={'no_tools':'无工具 LLM','single_rag':'单次 RAG','multi_step':'多步无验证','verified':'完整 Agent','verified_no_repair':'验证但不修复'}
ORDER=list(NAMES)

def main():
    audit=json.loads((RESULTS/'experiment-audit.json').read_text(encoding='utf-8'))
    assert audit['recorded_runs']==200 and audit['unique_tasks']==40 and audit['protocol_checks_passed']
    summary=json.loads((RESULTS/'summary.json').read_text(encoding='utf-8'))
    test_count=json.loads((ROOT/'docs/validation/tests.json').read_text(encoding='utf-8'))['passed']
    groups={g['mode']:g for g in summary['groups']}
    section=f'''## 6. 完成度与验证结果

### 6.1 按交付项核对

| 交付项 | 当前状态 | 验证依据 |
|---|---|---|
| Khoj 核心复用与来源记录 | 已实现 | 固定上游源码、抽取脚本、源文件哈希与许可证 |
| 文档导入、语义检索与资料库隔离 | 已实现并测试 | 本机实际导入、原文位置检查、自动化测试 |
| 规划、四类工具与有界控制 | 已实现并运行 | 真实模型 trace、实时网页工具测试、预算审计 |
| 证据台账、独立检查与补检索 | 已实现并运行 | 真实演示和开发集扰动记录 |
| 本地界面、历史、取消与导出 | 已部署并验证 | 浏览器实际操作、桌面/手机截图 |
| 180 道题与规范语料准备 | 已完成 | 61 个集合、995 篇文档、完整性清单 |
| HotpotQA 40 题 × 5 配置 | 已执行一次完整矩阵 | 200 个留出任务记录及官方自动评分 |
| 三次重复实验 | 未完成 | 本次每配置每题仅运行一次 |
| 预选八题的完整扰动对照 | 未执行 | 本次只做一道开发题的四种机制诊断 |
| FRAMES 100 题正式测试 | 未执行 | 120 道开发/测试题仍需时点/答案版本人工审阅 |
| 双人引用与任务盲评 | 工具已实现，标注未完成 | 盲评表、协调与汇总脚本；人工指标为空 |
| 本地生成模型备用方案 | 已安装并做引擎测试 | 真实 JSON 接口测试；未将其混入 DeepSeek 对照 |

### 6.2 软件与端到端验证

自动化测试实际通过 {test_count} 项。覆盖来源隔离、PDF 页码及文本范围、来源更新、引用与数字检查、精确引句、短答案门禁、补检索、消融配置、重复调用、重试、预算、取消、失败用量、地址限制和评测数据隔离。模型响应的单元测试采用可控模拟，因此测试数量不等同于真实模型正确率。

真实演示任务在 13.282 秒完成，调用模型 4 次、工具 4 次，输入 9,117、输出 2,127 tokens。它判断 Aurora 与 Boreal 的原始分数不可直接比较，报告可点击查看五段保存原文。检查器将 A0 与六条候选结论标为 supported；这仅是自动检查结果，不是 100% 人工引用精度。

实际浏览器验证包括导入、已保存任务深链接、引用弹窗、台账、轨迹、JSON 导出和手机布局。另一次允许联网的完整研究任务在 19.094 秒完成，实际执行 search_web 和 read_webpage，基于原始论文页面回答 RAG 2020 论文及两类记忆的问题；五次模型调用产生 16,963 个输入和 2,096 个输出 tokens。该演示独立保存在 docs/validation/live-web-run.json，不计入固定语料实验。它证明当时实时流程可用，不代表长期网页可靠性。备用 Qwen2.5-1.5B 在本机 Vulkan GPU 上通过一次 JSON 引擎探测，未进行完整课程评测。

### 6.3 冻结后的留出集结果

以下为官方公开 development split 中预先选定的 40 道 HotpotQA 留出题，不是官方隐藏测试榜单。五配置各运行一次，共 200 个任务。应用源码哈希、模型、嵌入和预算在运行前冻结；实验期间未调提示词，未执行网页工具。失败任务保留在分母中。指标按 0-100% 展示。表中的端到端延迟包含提交、排队、轮询与 HTTP 开销，不含预先下载和建库；服务端纯执行时间另保存在结果文件中。

| 配置 | Answer EM | Answer F1 | 支持事实 F1 | 失败任务 |
|---|---|---|---|---|
'''
    for mode in ORDER:
        g=groups[mode]
        section+=f"| {NAMES[mode]} | {g['answer_em']*100:.1f}% | {g['answer_f1']*100:.1f}% | {g['supporting_f1']*100:.1f}% | {g['failed_runs']}/40 |\n"
    section+='''
支持事实 F1 衡量最终引用到的原始句子与官方支持句标签的重叠，不等同于人工语义引用支持精度。

| 配置 | 端到端中位秒数 | P95（秒） | 每题 token 中位数 | 拒答任务 |
|---|---|---|---|---|
'''
    for mode in ORDER:
        g=groups[mode]
        section+=f"| {NAMES[mode]} | {g['client_end_to_end_median_seconds']:.2f} | {g['client_end_to_end_p95_seconds']:.2f} | {g['tokens_median']:,.0f} | {g.get('abstained_runs',0)}/40 |\n"
    section+=(f"\n本次留出矩阵累计 {audit['model_calls_total_latest_attempts']:,} 次模型请求，"
             f"{audit['input_tokens_total_latest_attempts']:,} 个输入 tokens、{audit['output_tokens_total_latest_attempts']:,} 个输出 tokens。"
             "这些数值包含各任务的检查和已记录失败尝试；开发调试与引擎探测单独记录，不混入该矩阵。未配置带日期的计费单价，故美元费用保持为空。\n\n")
    full,multi=groups['verified'],groups['multi_step']
    section+=(f"完整 Agent 相对多步无验证的 Answer EM 差值为 {(full['answer_em']-multi['answer_em'])*100:+.1f} 个百分点，"
              f"支持事实 F1 差值为 {(full['supporting_f1']-multi['supporting_f1'])*100:+.1f} 个百分点，"
              f"每题 token 中位数之比为 {full['tokens_median']/multi['tokens_median']:.2f}。"
              "这些结果需同时结合回答率、拒答与人工检查解释；不把更保守或更少回答自动视为更好。\n\n")
    em_interval=next(c for c in summary['paired_comparisons'] if c['metric']=='answer_em')
    section+=(f"本次结果是负面发现：完整验证流程没有带来自动答案指标的提升。EM 差值的任务级配对 bootstrap 95% 区间为 "
              f"[{em_interval['ci95'][0]*100:.2f}, {em_interval['ci95'][1]*100:.2f}] 个百分点。"
              "检查器误判、格式约束和额外拒答可能影响覆盖与答案表现，需要逐题人工审阅才能区分原因；不能以其更复杂或更昂贵来宣称更可靠。\n\n")
    section+='''任务级配对 bootstrap 95% 区间保存在 summary.json 的 paired_comparisons 中。40 道公开题、单次运行且无双人语义评分，无法单独证明 proposal 的主假设；应报告负面结果和不确定性。

### 6.4 开发集与扰动诊断

最终开发小样本为两题五配置，共十次运行，另有四个扰动运行。开发实验中，完整 Agent 的 Answer EM 为 50%，与多步无验证相同；两者服务端执行时间中位数分别为 10.586 秒和 5.797 秒。该小样本用于发现协议问题，不应作为泛化成绩。

同一道开发题的 timeout、empty 和 irrelevant 场景均完成并返回正确短答案；移除支持句的场景返回空答案，保留未解决事项。四种场景分别耗时 10.782、10.718、8.688 和 10.297 秒。它们验证了重试、补检索和拒答机制，但只有一道题，也没有两位审阅者核验剩余证据，不能宣称普遍恢复率或正确拒答率为 100%。

### 6.5 已观察到的失败与局限

开发题中出现“style”与金标准“oil on canvas”的口径歧义：无验证回答将同一艺术家的其他作品信息推为被问画作的风格，完整模式拒绝了未被相关段落支持的推断。自动 EM 给拒答零分；这应作为需要人工语义协调的案例，而不是直接宣布拒答一定正确。

留出集逐题配对中，二十题两种多步模式都满足 EM，六题只有无验证模式满足，一题只有完整模式满足，十三题均不满足。一个修复成功的例子通过歌曲作者 Future、真实姓名 Wilburn 与出生地段落之间的连接找到了 Atlanta, Georgia；一个明显需要复核的错误把键盘手 Luis Resto 与合作的说唱歌手 Eminem 的角色混淆，却仍被检查器标为支持。这些事后案例保存在 paired-outcomes-and-cases.json，没有据此修改模型或分数。

另有题目把 Canberra 喷气轰炸机与二战西南太平洋战区联系起来，但引用材料写的是该飞机在二十世纪五十年代制造，某部队在二战作战，之后才装备 Canberra。完整模式因时间关系未得到支持而拒答，原始 EM 仍为零。这提示部分金标准或题目关系可能存在噪声；当前未重评分，需双人复核，不能把全部 EM 降幅直接等同于事实可靠性下降。

演示 A0 的自动检查理由承认“缺少完整结果表”这一部分未被直接证明，却仍以核心比较结论成立为由标为 supported。这是检查器可能放过部分未支持内容的实际案例。精确引文存在检查没有解决全部语义蕴含问题，不能把界面绿色标签直接计作人工金标准。

开发阶段还发现云端账户余额不足，以及默认 thinking 消耗输出预算导致结构化内容为空的问题。余额恢复后已重试；最终冻结配置显式禁用官方 DeepSeek API 的 thinking，所有配置使用相同短答案格式和 token 上限。早期调试记录保留在独立目录，不混入最终留出结果。

### 6.6 尚未完成的实验工作

尚未完成三次重复、预选八题的完整扰动对照、FRAMES 时点/版本人工审阅及正式测试、双人引用盲评与证据不足条件核验。相应人工指标和主假设结论保持未定。软件、数据和复现脚本已经交付，可以继续这部分课程研究，但不应把它写成已经取得的实验成果。

'''
    path=ROOT/'docs/PROJECT_REPORT.zh-CN.md'
    text=path.read_text(encoding='utf-8')
    start=text.index('## 6. 完成度与验证结果')
    end=text.index('## 7. 本地部署')
    path.write_text(text[:start]+section+text[end:],encoding='utf-8')
    print('Report updated from audited 200-run held-out matrix.')

if __name__=='__main__':main()
