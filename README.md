# Khoj Research Lab

COMP7608B Group 30 · Evidence-Grounded Personal Research with a Tool-Using AI Agent

[Retrieval modes and server comparison guide](docs/RETRIEVAL.md)

这是根据小组 proposal 实现的个人研究助手：导入文档，提出多部分问题，查看有逐条引用的报告、证据检查结果、补检索过程和未解决问题。提供四个主要实验配置及一个禁用修复的消融配置。

本地界面为 <http://127.0.0.1:8778>。完整说明见 [项目报告](docs/PROJECT_REPORT.zh-CN.md)、[PDF 报告](docs/Khoj-Research-Lab-Report.pdf)、[数据与实验](docs/DATASET.md)、[上游改动](docs/UPSTREAM.md)。

2026-11-17 的联网研究与无答案反馈修复见 [更新记录](docs/UPDATES-2026-11-17.md)。原报告中的 200 次实验属于 2026-11-16 冻结版本；本次修复未改写历史结果。

## 从 GitHub 部署

```powershell
git clone https://github.com/kz0321/khoj-research-lab.git
Set-Location khoj-research-lab
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -Python '你的 Python 3.10–3.12 可执行文件完整路径'
```

安装后在本机编辑 `.env`，配置模型服务地址、模型名和 API 密钥；该文件不会提交到 GitHub。然后双击 `Start-Khoj-Research-Lab.cmd`，或执行下面的启动命令。首次安装需要网络下载依赖及嵌入模型，应用服务仅在本机运行。

仓库包含课程代码、固定版本上游源码、规范评测数据、实验记录、部署脚本和公开版报告。报告保留成员姓名，移除了学号。历史实验对应的应用源码另存于 [冻结版本](reproducibility/frozen-app-20261116/README.md)。

## 分支与后续更新

- `main`：默认展示与稳定版本。
- `test`：后续开发、测试和更新，从首次发布的同一提交建立。

```powershell
git switch test
git pull --ff-only origin test
# 修改代码并验证后，再按需提交：
git add <需要提交的文件>
git commit -m "Describe the update"
git push origin test
```

更新确认后，在 GitHub 创建从 `test` 到 `main` 的 Pull Request。不要提交 `.env`、`runtime/`、模型权重或虚拟环境。

## 与 Khoj 的关系

固定上游 [khoj-ai/khoj](https://github.com/khoj-ai/khoj) commit `ae229ca894c0b80ad84664afcfdde523b5e87057`。实际复用并适配了 Markdown 分节器、研究规划提示词、四种工具定义、研究迭代协议、重复调用检查与工具历史格式。代码位于 `app/khoj_core.py`，有来源说明和可复现抽取脚本。

这是 **Khoj 核心代码的 Windows 课程适配版**。本地运行的不是完整 Khoj Django/PostgreSQL/pgvector 产品栈；存储、检索、证据验证与界面由本项目实现。完整上游源码保留在 `upstream/khoj/`，未混入课程改动。衍生代码遵循 AGPL-3.0-or-later，数据和模型分别遵循其自身许可证。

## 安装后的启动与停止

打开 PowerShell：

```powershell
# 在克隆后的 khoj-research-lab 目录执行
.\scripts\start.ps1 -OpenBrowser
```

这会使用本地 `.env` 中的模型配置。运行记录、文本索引和日志保存在 `runtime/`，停止后仍保留：

```powershell
.\scripts\stop.ps1
```

也可以双击项目根目录的 `Start-Khoj-Research-Lab.cmd` 启动并打开浏览器，双击 `Stop-Khoj-Research-Lab.cmd` 停止。已保存的演示结果位于 `docs/validation/`；运行数据库不随仓库分发，首次部署后请按下文“五分钟演示”重新运行示例。

本地开源模型备用模式：

```powershell
.\.venv\Scripts\python.exe scripts/setup_local_model.py
.\scripts\start_local_model.ps1
.\scripts\stop.ps1
.\scripts\start.ps1 -LocalModel -OpenBrowser
```

备用模式通过启动环境变量覆盖模型配置，不会覆盖 `.env` 中原有 API 密钥。切回云端：停止应用后，使用不带 `-LocalModel` 的 `start.ps1` 启动。切换前等待当前研究结束。

备用引擎已验证启动、一次结构化 JSON 调用与停止；尚未验证 Qwen 小模型完成整个 Agent 研究流程，CPU 后端也未进行推理测速。详见 [本地模型验证记录](docs/LOCAL_MODEL.md)。若 Vulkan 不可用，停止备用引擎后可使用 `scripts/start_local_model.ps1 -Backend cpu`。

## 在另一台 Windows 电脑安装

1. 安装 Python 3.10、3.11 或 3.12。当前电脑用 Python 3.10.22；不要使用默认的 Python 3.14 创建环境。
2. 解压代码到可写目录，进入项目根目录。
3. 运行 `scripts/setup.ps1 -Python '你的Python完整路径'`。脚本安装锁定依赖并下载英语嵌入模型，首次需要网络。
4. 在本地编辑 `.env`，设置 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_KEY`。密钥不在交付代码包中。也可使用上面的本地模型模式。
5. 执行 `scripts/start.ps1 -OpenBrowser`。浏览器访问 <http://127.0.0.1:8778>。

如果 PowerShell 阻止运行脚本，可对单次进程使用：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

无需管理员权限、Docker、数据库服务器或模型训练。完整运行依赖 `requirements-lock.txt`，直接依赖及 Python 版本见 `pyproject.toml`。首次嵌入模型下载约几十 MB；可选生成模型会另外下载约 1 GB，具体清单见 `docs/local-model-manifest.json`。

## 五分钟演示

1. 点击左侧“载入示例资料库”。其中五份 Markdown 是明确标注的合成教学资料，不是论文真实实验数据。
2. 输入：`Compare Aurora and Boreal. Are their reported scores directly comparable, and what evidence is still missing?`
3. 选择“完整 Agent：证据检查 + 修复”，关闭联网检索，开始研究。
4. 点击报告中的 `[E1]` 等引用，查看原文、来源和位置；切换“证据台账”查看候选声明被支持、反驳或判为证据不足的原因。
5. 查看“行动轨迹”和用量，下载 JSON 或 Markdown。未通过验证的候选声明仍保留在台账，正式报告不将其展示为已支持结论。

这组示例应引导系统发现实验所用数据集、指标截断、硬件与 reranker 设置不同，不能直接比较原始分数。系统的实际输出仍取决于模型；样例预期不是硬编码答案。

## 自己的资料

创建资料库，再拖入 TXT、Markdown、文本 PDF、DOCX 或 HTML。每批最多 20 个文件，每个最多 10 MB。PDF 最多 200 页；扫描 PDF 不含可提取文字时会明确失败，需要先做外部 OCR。

文件被解析为文本与带位置的片段，写入 SQLite；上传原文件本身不另外存档，请保留原件。重复上传同名文件会替换该资料库中的旧文本和索引。资料库之间检索隔离。

当前嵌入模型 BGE-small-en 面向英语，是两个评测数据集的语言；中文界面不代表中文语义检索已经做过质量评测。采用云端模型时，问题及检索到的相关文本会发送到该模型 API；采用本地模型时，生成与嵌入均在本机。联网开关只控制网页搜索/读取，不控制云端模型调用。

## 实验配置

| 模式 | 行为 |
|---|---|
| `no_tools` | 同一生成模型直接回答，不读资料库 |
| `single_rag` | 一次检索，再生成引用回答 |
| `multi_step` | 多步工具使用，不进行显式证据验证 |
| `verified` | 多步检索、结构化检查、最多两轮补检索和重新检查 |
| `verified_no_repair` | 保留检查，但不触发补检索 |

默认上限：六轮决策、十二次实际工具尝试（包括重试）、两轮修复、十六次实际模型请求。云端默认 240 秒，本地小模型模式 900 秒。停止与取消在操作边界检查；已发出的 API 请求可能先结束，迟到结果不会作为成功结果接受。

## 验证与实验命令

```powershell
.\.venv\Scripts\python.exe scripts/doctor.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m eval.check_data
.\.venv\Scripts\python.exe -m eval.run --dataset hotpotqa --split dev --limit 2 --output eval/results/my-dev-pilot
```

最后一条会真实调用当前模型，在开发集的两道题上运行五种配置。完整实验、官方 HotpotQA 评分、双人盲评、配对 bootstrap、扰动和数据许可见 `docs/DATASET.md`。没有人工标注时，引用支持率等字段保留为空，不能用验证器自己的判断替代人工标准。

## 常见问题

- **HTTP 402**：模型账户余额不足；补充余额、换可用配置，或切换本地模型。检查 `/models` 成功不能证明生成接口有余额。
- **HTTP 401/403**：检查本地密钥、服务地址与权限；不要把密钥贴进 issue、截图或报告。
- **导入首次较慢**：首次加载/下载嵌入模型；大语料需要计算并持久化向量。运行日志见 `runtime/server.stderr.log`。
- **证据不足**：检查问题是否超出资料、原文是否解析完整、引用是否真的包含必需事实；可补充文档或明确开启联网。
- **网页失败**：公开搜索站点可能限流或反爬；工具记录失败，系统不能把搜索摘要当成原文证据。固定语料实验禁用联网。
- **端口冲突**：本项目未运行时可使用 `scripts/start.ps1 -Port 8779`，并在评测命令中用相同 `--api` 地址。若已有本项目进程，应先等待当前研究结束并停止后再换端口；不要让两个进程共用同一运行数据库。
- **重启中的任务**：重启时未完成任务标为失败，不会伪装为已完成，也不会自动重复收费。

应用仅绑定本机回环地址，无多用户认证；本课程部署不适用于直接暴露到公网。

## 重新生成报告与交付包

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-report.txt
.\.venv\Scripts\python.exe scripts/build_report.py
.\.venv\Scripts\python.exe scripts/package_project.py
```

报告源文件为 `docs/PROJECT_REPORT.zh-CN.md`。打包器包含规范数据集合、源码、上游源码和已保存结果，排除密钥、运行数据库、虚拟环境、下载模型和未引用的缓存；同时检查当前配置密钥是否意外出现在待交付文件中。
