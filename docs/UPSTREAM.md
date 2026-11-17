# Khoj 基座、代码来源与改动边界

本课程项目使用 Khoj 的真实开源源码作为基础，采用**抽取核心组件并适配本地运行环境**的方式。运行的应用不是未经修改的完整 Khoj 服务，也不包含其全部产品功能。

## 固定版本

- 源码仓库：https://github.com/khoj-ai/khoj
- 固定提交：`ae229ca894c0b80ad84664afcfdde523b5e87057`
- 本地完整源码：`upstream/khoj/`
- 上游许可：`AGPL-3.0-or-later`；原始许可证保存在项目根目录 `LICENSE`。
- 文件哈希与适配文件哈希：`docs/upstream-manifest.json`。
- 当前使用版本以此提交为准，不依赖随时变化的 `master` 或 `latest`。

## 实际复用的代码

| 上游位置 | 复用内容 | 本地实现 / 适配 |
| --- | --- | --- |
| `src/khoj/processor/conversation/utils.py` | `ToolCall` 与 `ResearchIteration` 的工具调用、观测、警告和序列化协议 | `app/khoj_core.py`；`ToolCall` 原样抽取，`ResearchIteration` 移除本项目不用的计算机操作和代码沙箱上下文 |
| `src/khoj/utils/helpers.py` | `ToolDefinition`、`dict_to_tuple`、四类真实工具的定义及 JSON 参数模式 | `app/khoj_core.py`；保留 `semantic_search_files`、`view_file`、`search_web`、`read_webpage` 工具名称和参数语义 |
| `src/khoj/processor/conversation/prompts.py` | `plan_function_execution` 多步骤研究规划提示词 | `build_planning_prompt()`；去除 LangChain 模板依赖，把“只在完成任务时停止”改为允许证据不足和预算耗尽时停止，并追加来源不能作为指令的要求 |
| `src/khoj/routers/research.py` | 已成功执行的工具与参数组合去重规则 | `detect_repeated_tool()`；失败重试次数和总预算由课程控制器管理 |
| `src/khoj/processor/content/markdown/markdown_to_entries.py` | `process_single_markdown_file()` 递归 Markdown 标题解析与父标题上下文保留 | `markdown_sections()`；保留标题遍历算法，修复可变默认参数，并限制畸形标题的查找循环 |
| `src/khoj/processor/conversation/utils.py` | 迭代历史转模型上下文的做法 | `construct_iteration_history()` 将依赖 Django/供应商类的实现改为普通 OpenAI 兼容消息字典；保留工具调用 ID 和明确的失败观测 |

`markdown_sections()` 的 `compiled` 字段可能包含 Khoj 自动添加的父标题，仅供检索上下文使用。其 `text` 字段严格来自原文连续行，附带 `start_line`、`end_line`，只有原文应作为逐字证据。后续分块仍需根据所用嵌入模型的长度限制执行。

上述复用不通过伪造同名包、运行时 monkey patch 或仅展示上游仓库链接实现。`app/khoj_core.py` 是实际可导入、可测试的执行代码；`scripts/vendor_khoj_core.py` 从固定上游提交使用 Python AST 抽取指定定义，不会执行整个上游应用。工具处理器、检索后端和验证器则由本项目实现。

## 课程项目新增部分

与上游相比，本项目重点增加：证据台账；来源与原文位置校验；数值检查和独立语义验证；支持 / 矛盾 / 证据不足三态；验证驱动的补检索；严格的决策轮数、工具数、修复次数与时间预算；受控实验配置、追踪导出和引用检查界面。具体实现和实际验证状态以交付报告为准。

## 为什么采用这一部署方式

当前 Khoj 完整服务需要 Python `>=3.10,<3.13`、Django、PostgreSQL 和 pgvector，另有 PyTorch、语音、OCR、多供应商 SDK 及其他依赖。官方 Windows 文档推荐 Docker / WSL2；原生 pgvector 可能需要额外编译工具。其可选 `pgserver` 分支使用 Unix socket，不能直接替代 Windows 数据库部署。

因此，本地课程版采用独立的轻量 Web 进程、文件/SQLite 存储和可替换模型接口，在无 Docker 的 Windows 环境中运行。它保留上述 Khoj 核心实现，并以明确的新后端替代完整产品的数据库、身份管理和工具基础设施。此取舍不应描述成“已部署 Khoj 全套服务”。

若今后迁移回完整 Khoj，可将课程控制器接到 `src/khoj/routers/research.py` 的 `execute_tool()` 观测之后、最终回答之前，通过 `EntryAdapters` 接入上游文档检索，并把当前台账存储迁移为 Django 模型。该迁移路径是扩展说明，不代表已经完成的集成。

## 验证与重新抽取

在项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\prepare_upstream.ps1
# 只有未提供完整 upstream 目录时才需要下载：
powershell -ExecutionPolicy Bypass -File .\scripts\prepare_upstream.ps1 -CloneIfMissing

# 使用项目 Python 环境重新生成核心文件与来源清单：
.\.venv\Scripts\python.exe .\scripts\vendor_khoj_core.py
```

源码压缩包不包含 `.git`。验证脚本对 Git checkout 检查固定提交和工作区状态；对压缩包中的源码树，则依据 `docs/upstream-manifest.json` 校验实际复用的五个源码文件及许可证哈希，无需安装 Git。其他上游文件的归档完整性由 `DELIVERY-MANIFEST.json` 记录。文件校验失败时不会覆盖或重新克隆到已有目录。

重新抽取默认会覆盖 `app/khoj_core.py` 和来源清单，开发改动应先同步到抽取脚本。评测冻结后可使用只读检查，或把比较版本写入单独目录而不改动应用：

```powershell
.\.venv\Scripts\python.exe .\scripts\vendor_khoj_core.py --check-only
.\.venv\Scripts\python.exe .\scripts\vendor_khoj_core.py --output-dir .\comparison-extraction
```

## 许可与分发

本项目包含并修改 AGPL 代码，项目衍生代码按 `AGPL-3.0-or-later` 提供，保留上游署名和源码。分享该应用或提供网络服务时，应依许可证提供对应源码。模型权重、基准数据和第三方库各自遵守其独立许可，不能仅以本项目的 AGPL 许可代替；参见 `THIRD_PARTY_NOTICES.md` 与各下载清单。
