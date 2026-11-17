# Research report

Compare Aurora and Boreal. Are their reported scores directly comparable, and what evidence is still missing?

## Answer

No. Aurora's 72.0% Recall@5 on Dataset River v1 (500 questions, BM25, no reranker, CPU) and Boreal's 84.0% Recall@10 on Dataset Forest v2 (800 questions, dense retriever with cross-encoder reranker, GPU) differ in dataset, metric cutoff, reranker setting and hardware, so they are not directly comparable; a controlled head-to-head evaluation, common-corpus follow-up, full results tables and citation-support precision measurements are still missing. [E1] [E2] [E3] [E4]

## Supported findings

- Aurora is a BM25 lexical retrieval study reporting 72.0% Recall@5 on Dataset River v1 with 500 English questions, no reranker, and an eight-core CPU. [E3]
- Boreal is a dense embedding retrieval study reporting 84.0% Recall@10 on Dataset Forest v2 with 800 English questions, a cross-encoder reranker, and a GPU. [E4]
- A direct accuracy comparison requires the same dataset version, question split, corpus, relevance labels and metric cutoff, and Recall@5 and Recall@10 measure different operating points. [E2]
- The reviewer rejected the superiority claim because datasets, metric cutoffs, hardware and reranker settings differ, and the team withdrew it. [E1]
- No common-corpus follow-up experiment has been completed, and the required controls have not yet been applied jointly to Aurora and Boreal; a controlled head-to-head evaluation is still required. [E1] [E2]
- Neither study reports the final answer citation-support precision, and Boreal's publication did not measure evidence-grounded answer quality. [E1] [E4]

## Unresolved questions

- No full results tables or detailed methodology appendices for either study are present in the supplied evidence.
- No common-corpus or controlled head-to-head evaluation results exist in the evidence.
- No citation-support precision or evidence-grounded answer quality measurements are reported for either system.

## Evidence

### [E1] 04-lab-notes.md
{"start_line": 1, "end_line": 9, "section_start_char": 0, "section_end_char": 543, "heading": "# Lab meeting notes"}

> # Lab meeting notes
> This is a synthetic teaching document.
> 
> ## Draft interpretation
> The team initially wrote that Boreal's reported 84.0% score proved it outperformed Aurora's reported 72.0% score. This was an unreviewed interpretation.
> 
> ## Correction
> The reviewer rejected that conclusion because the datasets, metric cutoffs, hardware and reranker settings differ. The team agreed to withdraw the superiority claim. No common-corpus follow-up experiment has been completed. Neither study reports the final answer citation-support precision.
> 

### [E2] 03-comparison-protocol.md
{"start_line": 1, "end_line": 9, "section_start_char": 0, "section_end_char": 709, "heading": "# Retrieval comparison protocol"}

> # Retrieval comparison protocol
> This is a synthetic teaching document.
> 
> ## Required controls
> A direct accuracy comparison requires the same dataset version, question split, corpus, relevance labels and metric cutoff. Recall@5 and Recall@10 measure different operating points. A higher Recall@10 on a different dataset does not establish a better retrieval method. A comparison should also state whether a reranker is used.
> 
> ## Runtime controls
> Latency comparisons must use the same hardware, corpus size, batch size and timing boundary. Indexing cost should be reported separately. These controls have not yet been applied jointly to Aurora and Boreal. A controlled head-to-head evaluation is still required.
> 

### [E3] 01-aurora-study.md
{"start_line": 1, "end_line": 9, "section_start_char": 0, "section_end_char": 568, "heading": "# Aurora lexical retrieval study"}

> # Aurora lexical retrieval study
> This is a synthetic teaching document, not a published scientific result.
> 
> ## Experiment
> Aurora uses BM25 lexical retrieval. The experiment used Dataset River v1 with 500 English questions. The metric was Recall@5. Aurora achieved 72.0% Recall@5 on Dataset River v1. There was no reranker. Measurements were made on 2025-03-01 using an eight-core CPU.
> 
> ## Latency
> The median retrieval latency was 18 ms per query, excluding document indexing. The corpus contained 10,000 passages. No generation model was evaluated in this experiment.
> 

### [E4] 02-boreal-study.md
{"start_line": 1, "end_line": 9, "section_start_char": 0, "section_end_char": 593, "heading": "# Boreal semantic retrieval study"}

> # Boreal semantic retrieval study
> This is a synthetic teaching document, not a published scientific result.
> 
> ## Experiment
> Boreal uses a dense embedding retriever. The experiment used Dataset Forest v2 with 800 English questions. The metric was Recall@10. Boreal achieved 84.0% Recall@10 on Dataset Forest v2. A cross-encoder reranker was applied. Measurements were made on 2025-04-15 using a GPU.
> 
> ## Latency
> The median retrieval latency was 24 ms per query, excluding document indexing. The corpus contained 50,000 passages. The publication did not measure evidence-grounded answer quality.
> 

### [E5] 05-evidence-checking.md
{"start_line": 1, "end_line": 9, "section_start_char": 0, "section_end_char": 767, "heading": "# Evidence checking handbook"}

> # Evidence checking handbook
> This is a synthetic teaching document.
> 
> ## Claim-level checks
> A citation must support the associated claim, not merely discuss the same topic. Numerical matching is necessary for literal score claims but does not validate experimental comparability. A system should distinguish supported findings, direct contradictions, and missing information. When essential information is missing, it should state the limitation instead of inventing an answer.
> 
> ## Project question
> Can explicit checking improve support precision without materially reducing answer completeness? The current demo documents do not contain measured results answering this research question. That claim requires the project's controlled evaluation and human annotations.
> 
