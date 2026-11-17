# Research report

RSI-Index（RSIGym，Recursive Self-Improvement，递归自我改进）有哪些现存的相关工作？请区分 RSI-Index 本身与递归自我改进领域的相关研究，列出论文或项目名称、主要贡献和来源链接。

## Answer

现有证据中，RSI-Index 是 RSIGym 论文（arXiv:2610.10310）定义的评估指标，而非一个独立项目；RSIGym 是配套的 agent-native 研究环境。递归自我改进领域的相关工作在证据中包括三篇综述：Awesome-RSI-Research 的《Towards AI That Improves Itself: A Survey of Recursive Self-Improvement》、arXiv:2607.07663《Recursive Self-Improvement in AI: From Bounded Self-Refinement to Autonomous Research Loops》和 arXiv:2610.35193《Trustworthy Recursive Self-Improvement in the Era of Large Models》。证据未提供 STOP、Gödel Agent、Darwin Gödel Machine、AlphaEvolve、SEAL、Self-Rewarding 等具体系统的名称、贡献或链接。 [E1] [E3] [E6] [E7] [E12] [E13] [E18] [E19]

## Supported findings

- RSI-Index 是 RSIGym 论文（arXiv:2610.10310）中定义的指标：五个基准上剩余性能差距被弥合的平均比例；RSIGym 是基于 Everything as a Service 的 agent-native 研究环境，支持 Data、Harness、Joint 改进轨道。 [E1] [E3]
- RSIGym 论文报告 Opus 5 在独立 Joint 运行中取得最高 RSI-Index 0.4809（每基准运行 500 美元平台服务预算），并将 SWE-bench Verified 从 17.67% 提升到 50.33%、AIME 从 31.67% 提升到 97.78%。 [E1]
- Awesome-RSI-Research 的综述《Towards AI That Improves Itself: A Survey of Recursive Self-Improvement》（作者 Hanjing Li、Qiguang Chen 等）界定 RSI 边界，区分 evolution、self-evolution、meta-evolution、recursive self-improvement 四阶段，以状态继承锚定递归，并提出 Proposal → Feedback → Optimization 循环。来源：https://lee1003-lee.github.io/Awesome-RSI-Research/ [E6] [E7]
- arXiv:2607.07663《Recursive Self-Improvement in AI: From Bounded Self-Refinement to Autonomous Research Loops》（Mingguang Chen、Licheng Wang、Bo Qu）调查 1,250 篇 2024–2026 年 arXiv 论文，沿“改进对象”和“闭环程度”两轴分类，区分有界自我精炼与开放式 RSI，并建立从形式验证器到内在自评的验证层级。来源：https://arxiv.org/abs/2607.07663 [E12] [E13]
- arXiv:2610.35193《Trustworthy Recursive Self-Improvement in the Era of Large Models: Foundation, Risks, Evaluation and Open Challenges》（Jiayue Pu 等）提出 RSI 的操作性定义与流程框架，将可信 RSI 要求组织为真实持续改进、行为约束/对齐/公平、系统安全与隐私、透明与可控四个主题。来源：https://arxiv.org/abs/2610.35193 [E18] [E19]
- 区分方式：RSI-Index 是 RSIGym 论文提出的量化评估指标（衡量跨五个基准的差距弥合比例），RSIGym 是其配套环境；而上述综述属于对 RSI 领域方法、分类与可信性要求的整体梳理，并非 RSI-Index 本身。 [E1] [E3] [E7] [E12] [E19]

## Unresolved questions

- 证据中未出现 STOP、Gödel Agent、Darwin Gödel Machine、AlphaEvolve、SEAL、Self-Rewarding 等具体 RSI 系统的名称、主要贡献或来源链接，因此无法列出这些条目。
- 未检索到除 RSIGym 论文外其他使用或定义 RSI-Index 的工作。

## Evidence

### [E1] [2610.10310] RSIGym: A Flexible Environment for Recursive Self-Improvement
{"start_char": 997, "end_char": 1996}

> Service (EaaS). RSIGym exposes training, inference, rollout, evaluation, and sandbox execution through reusable services, with shared budget and permission controls supporting Data, Harness, and Joint improvement tracks. This design enables agents to investigate individual interventions and jointly optimize data, training settings, and execution harnesses within the same environment. We define RSI-Index as the mean fraction of the remaining performance gap closed across five benchmarks covering software engineering, terminal interaction, mathematics, scientific reasoning, and skill-based tasks. Comparing six frontier research models in independent Joint runs, Opus 5 achieves the highest RSI-Index of 0.4809 under a $500 platform-service budget per benchmark run. Its selected systems improve all five benchmarks, raising SWE-bench Verified from 17.67% to 50.33% and AIME from 31.67% to 97.78%. Additional experiments examine DSH-harness refinement, budget variation, and restricted network 

https://arxiv.org/abs/2610.10310
### [E2] [2610.10310] RSIGym: A Flexible Environment for Recursive Self-Improvement
{"start_char": 1996, "end_char": 2989}

> access, while recorded trajectories reveal how agents diagnose failures and select candidates. We open-source the full RSIGym codebase and results to support reproducibility and further research.
> Subjects:
> Machine Learning (cs.LG)
> Cite as:
> arXiv:2610.10310
> [cs.LG]
> (or
> arXiv:2610.10310v1
> [cs.LG]
> for this version)
> https://doi.org/10.48550/arXiv.2610.10310
> Focus to learn more
> arXiv-issued DOI via DataCite
> Submission history
> From: Fanqing Meng [
> view email
> ]
> [v1]
> Wed, 7 Oct 2026 16:05:15 UTC (96 KB)
> Full-text links:
> Access Paper:
> View a PDF of the paper titled RSIGym: A Flexible Environment for Recursive Self-Improvement, by Fanqing Meng and 8 other authors
> View PDF
> HTML (experimental)
> TeX Source
> view license
> Additional Features
> Audio Summary
> Current browse context:
> cs.LG
> < prev
> |
> next >
> new
> |
> recent
> |
> 2026-10
> Change to browse by:
> cs
> References & Citations
> SciX
> Google Scholar
> Semantic Scholar
> export BibTeX citation
> Loading...
> BibTeX formatted citation
> ×
> loading...
> Data provided by:
> 

https://arxiv.org/abs/2610.10310
### [E3] [2610.10310] RSIGym: A Flexible Environment for Recursive Self-Improvement
{"start_char": 0, "end_char": 997}

> [2610.10310] RSIGym: A Flexible Environment for Recursive Self-Improvement
> Skip to main content
> Search arXiv
> Press Enter to search ·
> Advanced search
> Computer Science > Machine Learning
> arXiv:2610.10310
> (cs)
> [Submitted on 7 Oct 2026]
> Title:
> RSIGym: A Flexible Environment for Recursive Self-Improvement
> Authors:
> Fanqing Meng
> ,
> Lingxiao Du
> ,
> Haocheng Lu
> ,
> Qiguang Chen
> ,
> Ziqi Zhao
> ,
> Zijian Wu
> ,
> Jiayuan Zhuo
> ,
> Mengkang Hu
> ,
> Michael Qizhe Shieh
> View a PDF of the paper titled RSIGym: A Flexible Environment for Recursive Self-Improvement, by Fanqing Meng and 8 other authors
> View PDF
> HTML (experimental)
> Abstract:
> Recursive self-improvement requires carrying accepted changes into later improvement cycles, while studying agent-proposed changes also requires substantial research infrastructure. Existing settings often leave agents to rebuild routine infrastructure or restrict exploration to individual components. We introduce RSIGym, an agent-native research environment based on Everything as a 

https://arxiv.org/abs/2610.10310
### [E4] [2610.10310] RSIGym: A Flexible Environment for Recursive Self-Improvement
{"start_char": 3988, "end_char": 4759}

> Core recommender toggle
> CORE Recommender
> (
> What is CORE?
> )
> IArxiv recommender toggle
> IArxiv Recommender
> (
> What is IArxiv?
> )
> Author
> Venue
> Institution
> Topic
> About arXivLabs
> arXivLabs: experimental projects with community collaborators
> arXivLabs is a framework that allows collaborators to develop and share new arXiv features directly on our website.
> Both individuals and organizations that work with arXivLabs have embraced and accepted our values of openness, community, excellence, and user data privacy. arXiv is committed to these values and only works with partners that adhere to them.
> Have an idea for a project that will add value for arXiv's community?
> Learn more about arXivLabs
> .
> Which authors of this paper are endorsers?
> |
> Disable MathJax
> (
> What is MathJax?
> )

https://arxiv.org/abs/2610.10310
### [E5] [2610.10310] RSIGym: A Flexible Environment for Recursive Self-Improvement
{"start_char": 2989, "end_char": 3988}

> Bookmark
> Bibliographic Tools
> Bibliographic and Citation Tools
> Bibliographic Explorer Toggle
> Bibliographic Explorer
> (
> What is the Explorer?
> )
> Connected Papers Toggle
> Connected Papers
> (
> What is Connected Papers?
> )
> Litmaps Toggle
> Litmaps
> (
> What is Litmaps?
> )
> scite.ai Toggle
> scite Smart Citations
> (
> What are Smart Citations?
> )
> Code, Data, Media
> Code, Data and Media Associated with this Article
> alphaXiv Toggle
> alphaXiv
> (
> What is alphaXiv?
> )
> Links to Code Toggle
> CatalyzeX Code Finder for Papers
> (
> What is CatalyzeX?
> )
> DagsHub Toggle
> DagsHub
> (
> What is DagsHub?
> )
> GotitPub Toggle
> Gotit.pub
> (
> What is GotitPub?
> )
> Huggingface Toggle
> Hugging Face
> (
> What is Huggingface?
> )
> ScienceCast Toggle
> ScienceCast
> (
> What is ScienceCast?
> )
> Demos
> Demos
> Replicate Toggle
> Replicate
> (
> What is Replicate?
> )
> Spaces Toggle
> Hugging Face Spaces
> (
> What is Spaces?
> )
> Spaces Toggle
> TXYZ.AI
> (
> What is TXYZ.AI?
> )
> Related Papers
> Recommenders and Search Tools
> Link to Influence Flower
> Influence Flower
> (
> What are Influence Flowers?
> )
> 

https://arxiv.org/abs/2610.10310
### [E6] Towards AI That Improves Itself | RSI Survey
{"start_char": 0, "end_char": 998}

> Towards AI That Improves Itself | RSI Survey
> Survey paper
> Towards AI That Improves Itself
> A Survey of Recursive Self-Improvement
> Hanjing Li, Qiguang Chen, Chenyuan Zhang, Qionglin Qiu, Fanqing Meng,
>             Mengkang Hu, Libo Qin, Min Zhang
> Harbin Institute of Technology (Shenzhen)
> University of Hong Kong
> National University of Singapore
> Shanghai Innovation Institute
> Read PDF
> RSI moves from local revision toward persistent improvement loops across behavior,
>             agent systems, models, data, and research processes.
> 3-stage loop
> Proposal -> Feedback -> Optimization
> 4 evolution targets
> Behavior, agents, model/data, research
> 7 frontier dimensions
> Reliability through generalization
> Abstract
> From single-step revision to verifiable improvement loops
> Recent advances in agentic systems allow AI systems to conduct experiments,
>           interpret feedback, and modify their own workflows, transforming Recursive
>           Self-Improvement from a theoretical concept into an engineering 

https://lee1003-lee.github.io/Awesome-RSI-Research/
### [E7] Towards AI That Improves Itself | RSI Survey
{"start_char": 998, "end_char": 1995}

> problem.
>           Yet the field still lacks a unified account of what constitutes RSI and
>           how its improvement loop should be evaluated.
> This survey defines RSI boundaries, distinguishes four stages (evolution,
>           self-evolution, meta-evolution, and recursive self-improvement) and anchors
>           recursion in state inheritance: an accepted improvement
>           from one cycle becomes the starting state of a later cycle, while
>           “recursive progress” is reserved for the stronger claim that
>           the inherited state also improves the improver. It introduces a common
>           Proposal → Feedback → Optimization loop, organizes methods
>           across four evolution targets, and identifies research gaps around
>           evidence-based acceptance, reuse across cycles, and transfer beyond the
>           tasks or evaluators that produced the gains.
> Definition
> A common loop for modern RSI systems
> RSI is anchored in state inheritance: an improvement accepted in 

https://lee1003-lee.github.io/Awesome-RSI-Research/
### [E8] Towards AI That Improves Itself | RSI Survey
{"start_char": 4979, "end_char": 5971}

> Evolution
> Scientific operation agents, AI4AI, MLE, and end-to-end AI scientist systems
>                 automate the research loop around AI improvement.
> Scientific operation agents
> AI4AI and MLE
> End-to-end AI scientist systems
> An evidence ladder: from local repair to compounding
> Self-improvement claims differ in strength, and the ladder orders
>             them by the evidence each one needs.
> Local repair
> fixes the current output and stops there;
> persistent
>             transfer
> makes a change outlive the current run and help
>             later instances;
> recursive inheritance
> (the
>             minimal RSI claim) makes an accepted improvement the starting
>             state of a later cycle; and
> recursive progress
> further shows that the inherited state improves the improver itself.
> Causal attribution
> supplies the supporting evidence
>             (a counterfactual control against a frozen or no-retention
>             baseline) that a retained intervention, not an unrelated
>             

https://lee1003-lee.github.io/Awesome-RSI-Research/
### [E9] Towards AI That Improves Itself | RSI Survey
{"start_char": 7962, "end_char": 8367}

> evaluator?
> The strongest claim is transfer of the improvement procedure itself: later generations should search, evaluate, or optimize better because of what was retained.
> Recursive self-improvement has moved from theory to engineering practice;
>           the remaining challenge is to make its gains credible, reusable, and
>           transferable beyond the tasks and evaluators that produced them.
> Close

https://lee1003-lee.github.io/Awesome-RSI-Research/
### [E10] Towards AI That Improves Itself | RSI Survey
{"start_char": 1995, "end_char": 2993}

> one
>               cycle is retained as the starting state of a later cycle. Recursive
>               progress (the stronger claim that the inherited state also
>               improves the improver) is treated separately.
> Proposal
> Select an editable target and generate a candidate change through
>                   prompting, search, evolution, program synthesis, training, or experimentation.
> Target selection identifies what the loop is allowed to change.
> Candidate generation creates concrete artifacts such as prompts, tools, memory, code, data, or checkpoints.
> Feedback
> Expose consequences in a repository, simulator, benchmark, training run,
>                   or live environment, then convert outcomes into evidence.
> Execution environments reveal behavioral effects of a candidate.
> Verification signals judge the evidence through tests, rewards, model judges, formal checks, or review.
> Optimization
> Retain, revise, reject, promote, or roll back the candidate while preserving
>                   

https://lee1003-lee.github.io/Awesome-RSI-Research/
### [E11] Towards AI That Improves Itself | RSI Survey
{"start_char": 6966, "end_char": 7962}

> Diversity
> Do proposals cover meaningfully different hypotheses and execution paths?
> Diversity is about causal independence, not just different wording; systems should preserve disagreement, branch distance, and failure coverage.
> Persistence
> Does a successful intervention remain available and useful later?
> Retained artifacts need provenance, scope conditions, retirement criteria, and evidence that they contribute downstream rather than drifting into noise.
> Adaptability
> Can the system respond to changing tasks, tools, evaluators, and environments?
> The key split is frozen evidence for comparison versus adaptive evidence for discovering new weaknesses as the environment changes.
> Controllability
> Are authority, review, monitoring, and rollback coupled to risk?
> Update authority should track target scope, verifier strength, deployment context, and failure severity, with intervention points preserved across the loop.
> Generalization
> Does the improvement transfer beyond its original task and 

https://lee1003-lee.github.io/Awesome-RSI-Research/
### [E12] [2607.07663] Recursive Self-Improvement in AI: From Bounded Self-Refinement to Autonomous Research Loops
{"start_char": 997, "end_char": 1988}

> ambitions. We survey 1,250 arXiv papers (2024-2026) along two axes: what the system improves -- its behavior in deployment, its policy through training, its evaluator, or the research process itself -- and the degree of loop closure (human-in-the-loop to fully closed). The taxonomy separates bounded self-refinement -- convergent, evaluable, and industrial practice -- from open-ended recursive self-improvement (RSI), which remains bounded by grounding requirements, collapse dynamics, and compute constraints on every measured axis. Its distinctive feature is a dedicated category for self-evaluation: every improvement loop is a claim that some signal can substitute for human judgment. We survey the evaluator design space -- judges, process reward models, verifiers, rubrics, meta-evaluation -- order the signals into a verification hierarchy from formal verifiers (strongest) to intrinsic self-assessment (weakest), and observe that demonstrated self-improvement strength tracks this 

https://arxiv.org/abs/2607.07663
### [E13] [2607.07663] Recursive Self-Improvement in AI: From Bounded Self-Refinement to Autonomous Research Loops
{"start_char": 0, "end_char": 997}

> [2607.07663] Recursive Self-Improvement in AI: From Bounded Self-Refinement to Autonomous Research Loops
> Skip to main content
> Search arXiv
> Press Enter to search ·
> Advanced search
> Computer Science > Artificial Intelligence
> arXiv:2607.07663
> (cs)
> [Submitted on 8 Jul 2026 (
> v1
> ), last revised 6 Sep 2026 (this version, v2)]
> Title:
> Recursive Self-Improvement in AI: From Bounded Self-Refinement to Autonomous Research Loops
> Authors:
> Mingguang Chen
> ,
> Licheng Wang
> ,
> Bo Qu
> View a PDF of the paper titled Recursive Self-Improvement in AI: From Bounded Self-Refinement to Autonomous Research Loops, by Mingguang Chen and 2 other authors
> View PDF
> HTML (experimental)
> Abstract:
> AI systems increasingly participate in their own improvement: revising their outputs, adapting their harnesses during deployment, training on data they generate, and conducting AI research itself. This literature uses a vocabulary ("self-refine," "self-reward," "self-play," "self-evolve") that conflates fundamentally different 

https://arxiv.org/abs/2607.07663
### [E14] [2607.07663] Recursive Self-Improvement in AI: From Bounded Self-Refinement to Autonomous Research Loops
{"start_char": 2986, "end_char": 3986}

> Access Paper:
> View a PDF of the paper titled Recursive Self-Improvement in AI: From Bounded Self-Refinement to Autonomous Research Loops, by Mingguang Chen and 2 other authors
> View PDF
> HTML (experimental)
> TeX Source
> view license
> Additional Features
> Audio Summary
> Current browse context:
> cs.AI
> < prev
> |
> next >
> new
> |
> recent
> |
> 2026-07
> Change to browse by:
> cs
> References & Citations
> SciX
> Google Scholar
> Semantic Scholar
> export BibTeX citation
> Loading...
> BibTeX formatted citation
> ×
> loading...
> Data provided by:
> Bookmark
> Bibliographic Tools
> Bibliographic and Citation Tools
> Bibliographic Explorer Toggle
> Bibliographic Explorer
> (
> What is the Explorer?
> )
> Connected Papers Toggle
> Connected Papers
> (
> What is Connected Papers?
> )
> Litmaps Toggle
> Litmaps
> (
> What is Litmaps?
> )
> scite.ai Toggle
> scite Smart Citations
> (
> What are Smart Citations?
> )
> Code, Data, Media
> Code, Data and Media Associated with this Article
> alphaXiv Toggle
> alphaXiv
> (
> What is alphaXiv?
> )
> Links to Code Toggle
> CatalyzeX Code Finder for Papers
> 

https://arxiv.org/abs/2607.07663
### [E15] [2607.07663] Recursive Self-Improvement in AI: From Bounded Self-Refinement to Autonomous Research Loops
{"start_char": 1988, "end_char": 2986}

> hierarchy, that its failure modes (self-confirming loops, model and diversity collapse) follow from its violations, and that the "research direction-setting" bottleneck keeping humans in the loop divides into a verification problem the hierarchy indexes and a prior one -- choosing what deserves evaluation at all -- that it does not. We connect the literature to the theory of RSI limits and to the safety and governance questions raised by frontier-lab accounts of closing the loop, and identify governance-grade measurement of self-improvement as the field's most underpopulated niche.
> Comments:
> 44 pages, 6 figures
> Subjects:
> Artificial Intelligence (cs.AI)
> Cite as:
> arXiv:2607.07663
> [cs.AI]
> (or
> arXiv:2607.07663v2
> [cs.AI]
> for this version)
> https://doi.org/10.48550/arXiv.2607.07663
> Focus to learn more
> arXiv-issued DOI via DataCite
> Submission history
> From: Mingguang Chen [
> view email
> ]
> [v1]
> Wed, 8 Jul 2026 17:19:50 UTC (5,164 KB)
> [v2]
> Sun, 6 Sep 2026 11:44:06 UTC (5,189 KB)
> Full-text links:
> 

https://arxiv.org/abs/2607.07663
### [E16] [2607.07663] Recursive Self-Improvement in AI: From Bounded Self-Refinement to Autonomous Research Loops
{"start_char": 3986, "end_char": 4983}

> (
> What is CatalyzeX?
> )
> DagsHub Toggle
> DagsHub
> (
> What is DagsHub?
> )
> GotitPub Toggle
> Gotit.pub
> (
> What is GotitPub?
> )
> Huggingface Toggle
> Hugging Face
> (
> What is Huggingface?
> )
> ScienceCast Toggle
> ScienceCast
> (
> What is ScienceCast?
> )
> Demos
> Demos
> Replicate Toggle
> Replicate
> (
> What is Replicate?
> )
> Spaces Toggle
> Hugging Face Spaces
> (
> What is Spaces?
> )
> Spaces Toggle
> TXYZ.AI
> (
> What is TXYZ.AI?
> )
> Related Papers
> Recommenders and Search Tools
> Link to Influence Flower
> Influence Flower
> (
> What are Influence Flowers?
> )
> Core recommender toggle
> CORE Recommender
> (
> What is CORE?
> )
> Author
> Venue
> Institution
> Topic
> About arXivLabs
> arXivLabs: experimental projects with community collaborators
> arXivLabs is a framework that allows collaborators to develop and share new arXiv features directly on our website.
> Both individuals and organizations that work with arXivLabs have embraced and accepted our values of openness, community, excellence, and user data privacy. arXiv is committed to these values and only works 

https://arxiv.org/abs/2607.07663
### [E17] [2607.07663] Recursive Self-Improvement in AI: From Bounded Self-Refinement to Autonomous Research Loops
{"start_char": 4983, "end_char": 5198}

> with partners that adhere to them.
> Have an idea for a project that will add value for arXiv's community?
> Learn more about arXivLabs
> .
> Which authors of this paper are endorsers?
> |
> Disable MathJax
> (
> What is MathJax?
> )

https://arxiv.org/abs/2607.07663
### [E18] [2610.35193] Trustworthy Recursive Self-Improvement in the Era of Large Models: Foundation, Risks, Evaluation and Open Challenges
{"start_char": 0, "end_char": 994}

> [2610.35193] Trustworthy Recursive Self-Improvement in the Era of Large Models: Foundation, Risks, Evaluation and Open Challenges
> Skip to main content
> Search arXiv
> Press Enter to search ·
> Advanced search
> Computer Science > Artificial Intelligence
> arXiv:2610.35193
> (cs)
> [Submitted on 26 Oct 2026]
> Title:
> Trustworthy Recursive Self-Improvement in the Era of Large Models: Foundation, Risks, Evaluation and Open Challenges
> Authors:
> Jiayue Pu
> ,
> Ang Gao
> ,
> Jinyi Bai
> ,
> Qipeng Wang
> ,
> Tongyu Wen
> ,
> Jiahao Zhao
> ,
> Keyu Qu
> ,
> Junhao Zhang
> ,
> Chenglei Shen
> ,
> Zhongxiang Sun
> ,
> Jun Xu
> ,
> Xiao Zhang
> View a PDF of the paper titled Trustworthy Recursive Self-Improvement in the Era of Large Models: Foundation, Risks, Evaluation and Open Challenges, by Jiayue Pu and 11 other authors
> View PDF
> HTML (experimental)
> Abstract:
> AI systems built around large models increasingly use experience and feedback to make persistent changes to models, prompts, memories, tools, and workflows. Recursive self-improvement (RSI) 

https://arxiv.org/abs/2610.35193
### [E19] [2610.35193] Trustworthy Recursive Self-Improvement in the Era of Large Models: Foundation, Risks, Evaluation and Open Challenges
{"start_char": 994, "end_char": 1992}

> extends this process to inductive biases and to the mechanisms that govern future updates, which can themselves be revised and reused across improvement cycles. Yet self-modification alone does not guarantee trustworthy improvement. Reported gains may reflect flawed evaluations, previously acquired capabilities may deteriorate, and compliance with behavioral constraints may weaken. Compromised artifacts or sensitive information may also persist in successor systems. Changes to improvement mechanisms may invalidate earlier verification results and make human oversight less effective. This survey presents an operational definition and process framework for RSI and organizes the requirements for trustworthy RSI into four interconnected themes: genuine and sustained improvement; behavioral constraints, alignment, and fairness; system security and privacy; and transparency and controllability. We examine these themes from three perspectives: Improvement Validity, Constraint Preservation, 

https://arxiv.org/abs/2610.35193
### [E20] [2610.35193] Trustworthy Recursive Self-Improvement in the Era of Large Models: Foundation, Risks, Evaluation and Open Challenges
{"start_char": 2990, "end_char": 3989}

> Full-text links:
> Access Paper:
> View a PDF of the paper titled Trustworthy Recursive Self-Improvement in the Era of Large Models: Foundation, Risks, Evaluation and Open Challenges, by Jiayue Pu and 11 other authors
> View PDF
> HTML (experimental)
> TeX Source
> view license
> Additional Features
> Audio Summary
> Current browse context:
> cs.AI
> < prev
> |
> next >
> new
> |
> recent
> |
> 2026-10
> Change to browse by:
> cs
> cs.CR
> References & Citations
> SciX
> Google Scholar
> Semantic Scholar
> export BibTeX citation
> Loading...
> BibTeX formatted citation
> ×
> loading...
> Data provided by:
> Bookmark
> Bibliographic Tools
> Bibliographic and Citation Tools
> Bibliographic Explorer Toggle
> Bibliographic Explorer
> (
> What is the Explorer?
> )
> Connected Papers Toggle
> Connected Papers
> (
> What is Connected Papers?
> )
> Litmaps Toggle
> Litmaps
> (
> What is Litmaps?
> )
> scite.ai Toggle
> scite Smart Citations
> (
> What are Smart Citations?
> )
> Code, Data, Media
> Code, Data and Media Associated with this Article
> alphaXiv Toggle
> alphaXiv
> (
> What is alphaXiv?
> )
> Links to 

https://arxiv.org/abs/2610.35193
### [E21] [2610.35193] Trustworthy Recursive Self-Improvement in the Era of Large Models: Foundation, Risks, Evaluation and Open Challenges
{"start_char": 1992, "end_char": 2990}

> and Effective Oversight. This analysis covers improvement diagnosis, proposal generation, proposal evaluation, and update implementation (S1--S4), including the recursive application of these stages to improvement mechanisms (RI). We review risks, safeguards, and evaluation evidence for individual updates, effects inherited by successor systems, and revisions to improvement mechanisms, while distinguishing direct RSI findings from evidence in related systems. Finally, we examine evaluation settings, identify requirements for independent and longitudinal assessment, and discuss applications and open research problems.
> Subjects:
> Artificial Intelligence (cs.AI)
> ; Cryptography and Security (cs.CR)
> Cite as:
> arXiv:2610.35193
> [cs.AI]
> (or
> arXiv:2610.35193v1
> [cs.AI]
> for this version)
> https://doi.org/10.48550/arXiv.2610.35193
> Focus to learn more
> arXiv-issued DOI via DataCite (pending registration)
> Submission history
> From: Jiayue Pu [
> view email
> ]
> [v1]
> Mon, 26 Oct 2026 10:46:03 UTC (18,922 KB)
> 

https://arxiv.org/abs/2610.35193
### [E22] [2610.35193] Trustworthy Recursive Self-Improvement in the Era of Large Models: Foundation, Risks, Evaluation and Open Challenges
{"start_char": 3989, "end_char": 4987}

> Code Toggle
> CatalyzeX Code Finder for Papers
> (
> What is CatalyzeX?
> )
> DagsHub Toggle
> DagsHub
> (
> What is DagsHub?
> )
> GotitPub Toggle
> Gotit.pub
> (
> What is GotitPub?
> )
> Huggingface Toggle
> Hugging Face
> (
> What is Huggingface?
> )
> ScienceCast Toggle
> ScienceCast
> (
> What is ScienceCast?
> )
> Demos
> Demos
> Replicate Toggle
> Replicate
> (
> What is Replicate?
> )
> Spaces Toggle
> Hugging Face Spaces
> (
> What is Spaces?
> )
> Spaces Toggle
> TXYZ.AI
> (
> What is TXYZ.AI?
> )
> Related Papers
> Recommenders and Search Tools
> Link to Influence Flower
> Influence Flower
> (
> What are Influence Flowers?
> )
> Core recommender toggle
> CORE Recommender
> (
> What is CORE?
> )
> Author
> Venue
> Institution
> Topic
> About arXivLabs
> arXivLabs: experimental projects with community collaborators
> arXivLabs is a framework that allows collaborators to develop and share new arXiv features directly on our website.
> Both individuals and organizations that work with arXivLabs have embraced and accepted our values of openness, community, excellence, and user data privacy. arXiv 

https://arxiv.org/abs/2610.35193
### [E23] [2610.35193] Trustworthy Recursive Self-Improvement in the Era of Large Models: Foundation, Risks, Evaluation and Open Challenges
{"start_char": 4987, "end_char": 5246}

> is committed to these values and only works with partners that adhere to them.
> Have an idea for a project that will add value for arXiv's community?
> Learn more about arXivLabs
> .
> Which authors of this paper are endorsers?
> |
> Disable MathJax
> (
> What is MathJax?
> )

https://arxiv.org/abs/2610.35193