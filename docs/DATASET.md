# 数据、实验与人工评估说明

本文件描述已经准备好的数据与可运行评估脚本。数据准备、程序测试、真实模型开发集试运行、完整测试集实验和双人评估是不同完成项；不能互相替代。

## 已冻结的数据

随机种子为 `20261116`，原始问题不改写，重复问题在划分前排除。运行中的检索语料只接受正向白名单字段；参考答案、支持事实标签、问题到文档的正确对应关系保存在 `data/evaluation/`，不传给 Agent，也不导入文档库。

| 数据集 | 开发集 | 测试集 | 已准备语料 | 实际协议 |
|---|---:|---:|---:|---|
| FRAMES | 20 | 100 | 一个共享集合，395 篇来源文档 | 375 篇所选问题相关文档的去重并集，加 20 篇固定随机干扰文档 |
| HotpotQA | 20 | 40 | 60 个独立集合，每个 10 段，共 600 段 | 开发问题来自官方 train；测试问题来自已公开官方 development，即 Hugging Face validation |

FRAMES 按完整 reasoning-types 标签组合分组后循环抽样，固定种子打乱，先划分开发集，再从余下问题中取测试集。HotpotQA 从官方 split 的随机行号抽样，只接受十段上下文的 distractor 形式，不根据模型表现挑题。当前最终样本开发集为 16 bridge / 4 comparison，测试集为 34 bridge / 6 comparison。代码保留结构不符行的排除记录；当前最终清单的排除记录为空。

`data/manifests/frames.json` 和 `data/manifests/hotpotqa.json` 是权威清单。早期中断的准备工作可能留下未被清单引用的缓存/集合；评估器只按任务文件和清单导入，不遍历所有目录，也不把未引用材料算入实验。

准备清单中的 `status` 记录下载时的状态，作为冻结输入不随实验改写。实际实验完成情况应查看相应 `eval/results/<实验目录>/experiment-audit.json`；不能把准备状态和后续运行状态混为一谈。

### 版本与来源

- FRAMES：`google/frames-benchmark`，revision `58d9fb6330f3ab1316d1eca12e5e8ef23dcc22ef`。数据卡标为 Apache-2.0，见 `data/licenses/frames-dataset-card.md`。
- FRAMES Wikipedia 快照：`parasail-ai/frames-benchmark-wikipedia`，revision `7aae7084416224f1530aaae5b6fda673787f4122`。发布者说明采集于 2024 年 10 月；数据卡标为 CC-BY-SA-3.0 / GFDL，见对应 license/card 文件。来源 URL、文本 SHA256、上游 revision 保留在每篇文档中。
- HotpotQA：`hotpotqa/hotpot_qa`，revision `1908d6afbbead072334abe2965f91bd2709910ab`。数据卡标为 CC-BY-SA-4.0；保留 Wikipedia 标题、原始句子编号、来源 URL 与文本 SHA256。此子集不是官方隐藏测试集成绩。
- 官方 HotpotQA 评分脚本固定到 `hotpotqa/hotpot` commit `3635853403a8735609ee997664e1528f4480762a`。本地 `eval/vendor/hotpot_evaluate_v1.py` 仅将 `ujson` 导入改为标准库 `json`，计分逻辑不变；原始与修改后哈希见 `eval/vendor/SOURCE.json`。上游固定版本未提供根 LICENSE，保留作者与来源说明，勿把该脚本误标成项目自己的代码。

HotpotQA 的在线 rows API 不提供 revision 固定保证，所以本地保存的响应与 manifest/hash 定义本次冻结版本；不能仅凭 metadata revision 声称 API 响应完全钉住上游版本。FRAMES 原始 TSV 和快照 parquet 使用 revision URL 固定下载。

## 尚需人工完成的工作

FRAMES 的 2024 年 10 月快照不一定满足题目更早的时点。`data/evaluation/frames-temporal-audit.jsonl` 列出了逐题核验工作，当前标记为 pending。应查看保存的来源，确认必需事实、日期和答案版本，写入审阅者和备注，再将确认可评测的任务标为 `approved`。代码默认拒绝对尚未审阅的 FRAMES 任务宣称正式评测；`--allow-unreviewed-frames` 只允许诊断性试运行，输出记录明确保留这一限制。

引用支持精度、引用覆盖、完整任务成功、正确拒答和恢复率均需独立人工判断。不能用 checker 的 `supported` 标签充当标准答案。没有双人标注时，相应汇总字段为 `null`，不会生成虚假完成度或改善幅度。

## 使用已有数据进行试运行

在项目根目录打开 PowerShell，先启动本地服务，然后执行：

```powershell
.\.venv\Scripts\python.exe -m eval.run --api http://127.0.0.1:8778 --dataset hotpotqa --split dev --limit 2 --output eval/results/hotpot-dev-pilot
```

默认逐题顺序运行五个配置：`no_tools`、`single_rag`、`multi_step`、`verified`、`verified_no_repair`，只运行一次。每次请求都关闭实时网页访问。工具预算、模型、嵌入模型和检索参数来自同一个应用配置，模型调用与验证调用全部计入用量。运行文件包含实际输出、错误、trace、usage 与自动分数，配置与数据摘要保存在 `configuration.json`。

中断后使用完全相同命令可续跑已冻结配置中未完成的任务；变更数据、模型、预算、模式或场景时应选择新输出目录。调用端轮询超时会停止提交新任务，先检查服务端任务状态，避免不知情地重复付费。

默认保留失败记录，不自动重跑整个任务。显式添加 `--rerun-failures` 时会追加新的 attempt；质量指标取同一题目、模式、场景、重复编号的最后一次尝试，历史失败仍保留，token、调用数、估算费用和未知用量按所有尝试合计，报告额外尝试次数，不能通过重试隐藏成本。

如果服务返回模型鉴权、余额不足或模型不存在错误，评估器保存这一次失败后停止，不继续批量请求。服务健康检查或模型列表可读不代表真实生成已经可用；只有成功完成的真实请求才计入运行验证。

需要维护服务器时，可创建 `data/manifests/evaluation.pause` 空文件；评估器会保存当前任务结果后在任务之间安全退出。删除标记即可按相同命令继续。修改应用源代码或 thinking/结构化输出设置后必须使用新输出目录；配置记录还包含应用 Python 源文件的联合 SHA256，早期调试结果应单独保留。

诊断性 FRAMES 开发集运行：

```powershell
.\.venv\Scripts\python.exe -m eval.run --dataset frames --split dev --limit 1 --allow-unreviewed-frames --output eval/results/frames-dev-diagnostic
```

这会导入完整冻结的 395 篇文档，首次嵌入可能较慢。各个配置使用同一集合，不向 Agent 暴露当前题目的正确文档列表。

可先运行 `python -m eval.index_corpus --collection frames-frozen` 单独建立本地索引，不调用生成模型。进度与耗时写入 `data/manifests/indexing-trace.jsonl` 和对应 `*-local-index.json`。如需维护服务，在 `data/manifests/index.pause` 创建空文件，索引器会完成当前 5 篇文档的小批次后退出；删除这个标记再以同一命令续跑，服务端按稳定 ID 和内容哈希复用已有嵌入。

完整实验命令如下，只有准备好 API 预算、确认开发集配置冻结且完成 FRAMES 审阅后再执行；这些命令的存在不代表已经运行：

```powershell
.\.venv\Scripts\python.exe -m eval.run --dataset hotpotqa --split test --limit 0 --repeats 3 --output eval/results/hotpot-test-r3
.\.venv\Scripts\python.exe -m eval.run --dataset frames --split test --limit 0 --repeats 3 --output eval/results/frames-test-r3
```

总共 140 道测试题 × 5 配置 × 3 次，最多 2,100 个完整任务；一次任务可能多次调用模型，费用和延迟不可与 2,100 次单次生成混淆。

## 官方评分与人工盲评

```powershell
.\.venv\Scripts\python.exe -m eval.official_hotpot --runs eval/results/hotpot-dev-pilot/runs.jsonl --mode verified --split dev --output eval/results/hotpot-dev-pilot/official-verified
.\.venv\Scripts\python.exe -m eval.annotations export --runs eval/results/hotpot-dev-pilot/runs.jsonl --output eval/results/blind
```

官方评分按原始句子编号计算 answer EM/F1 和 supporting-fact F1。所有失败任务保留在分母中。仅把最终输出声明实际引用的证据映射成预测 supporting facts，不能把全部检索结果算作预测支持事实。被验证门禁剔除的候选声明只留在台账里，不计成最终输出声明。

完整运行矩阵结束后，可统一执行 `python -m eval.report_results --directory eval/results/hotpot-test-frozen-r1`。该命令只读取记录，不再调用模型；验证题目/模式/重复编号是否齐全、应用源码摘要是否改变、实际模型与预算是否一致、是否执行过实时网页工具，然后生成 `results-table.csv`、官方评分、实验审计与盲评表。矩阵未齐全时拒绝生成“完整实验”审计。已有人填写的盲评文件会受到保护，重新导出需使用新目录。

`rater-A.csv` 和 `rater-B.csv` 隐藏了系统模式、checker 结果与其理由。两位审阅者独立填写 `supported / unsupported / contradicted / not_verifiable`；`PRIVATE-system-key.json` 仅由实验负责人保管。先报告一致率和 Cohen's kappa，再解决分歧，形成含 `item_id,label,notes` 的 resolved CSV：

```powershell
.\.venv\Scripts\python.exe -m eval.annotations score --rater-a eval/results/blind/rater-A.csv --rater-b eval/results/blind/rater-B.csv --resolved eval/results/blind/resolved.csv --key eval/results/blind/PRIVATE-system-key.json --output eval/results/blind/human-scores.json
```

自动汇总提供任务级配对 bootstrap 95% 区间：先平均同一任务的多次运行，再以任务为重采样单位。开发小样本的区间只作描述，不足以证明 proposal 中 “+10 个百分点精度”等假设已达成。价格未配置时美元成本为 `null`，保留实际 token 数；失败且 API 未返回 usage 的调用单独计为未知用量。

另有 `task-rater-A.csv` 和 `task-rater-B.csv` 用于独立任务级判定，包含参考答案但去掉系统模式和验证器标签；应在引用盲评完成后使用。填写语义正确性、全部必需声明是否有证据、完整可访问语料是否足够、拒答是否正确和失败类别。经两人审阅与协调后，使用 `python -m eval.annotations score-tasks`，参数形式与上面的 `score` 一致，但 `--key` 指向 `PRIVATE-task-key.json`。该命令根据人工判断计算任务成功、正确拒答与扰动恢复率；空白表格不产生这些结论。

## 鲁棒性实验

`data/evaluation/hotpotqa-perturbations.jsonl` 预先固定了 8 个测试任务和四种场景，各配置使用同样任务和扰动：

- `timeout`：第一次检索工具尝试抛出一次超时，正常重试规则继续生效。
- `empty`：第一次检索尝试返回空列表。
- `irrelevant`：在工具响应中加入预定义无关文档。
- `withhold_support`：另建集合，删除官方标注的支持句，保留其他句子的原始编号；不会把被删除的内容告诉 Agent。

例：`python -m eval.run --dataset hotpotqa --split test --scenario timeout --limit 0 --output eval/results/robust-timeout`。干净结果与每种扰动结果分别汇总，不混合报告。删除官方支持句不等于其他上下文一定不足，拒答实验仍需要两位审阅者确认剩余材料无法解答。

开发阶段可使用 `--split dev --limit 1 --modes verified --scenario timeout --development-perturbations` 在固定的第一道开发题上验证扰动接口；其他场景同理。这样的诊断结果必须与相同配置、相同开发题的 clean 输出一起看，不能当作预先选定的 8 道测试题鲁棒性实验。

## 重新准备与核验

现有 JSONL 可直接使用；只有重新下载 FRAMES parquet 时才需要额外的 `pyarrow`：

```powershell
.\.venv\Scripts\python.exe -m pip install -r eval/requirements.txt
.\.venv\Scripts\python.exe -m eval.prepare_data --dataset all --seed 20261116
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_evaluation.py -v
```

缓存命中时不重新请求网络。输入格式、哈希与金标准隔离等由脚本和测试检查；人工语义与时点审阅仍是单独的必要工作。
