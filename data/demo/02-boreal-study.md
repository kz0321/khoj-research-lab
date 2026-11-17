# Boreal semantic retrieval study
This is a synthetic teaching document, not a published scientific result.

## Experiment
Boreal uses a dense embedding retriever. The experiment used Dataset Forest v2 with 800 English questions. The metric was Recall@10. Boreal achieved 84.0% Recall@10 on Dataset Forest v2. A cross-encoder reranker was applied. Measurements were made on 2025-04-15 using a GPU.

## Latency
The median retrieval latency was 24 ms per query, excluding document indexing. The corpus contained 50,000 passages. The publication did not measure evidence-grounded answer quality.
