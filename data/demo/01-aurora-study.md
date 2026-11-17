# Aurora lexical retrieval study
This is a synthetic teaching document, not a published scientific result.

## Experiment
Aurora uses BM25 lexical retrieval. The experiment used Dataset River v1 with 500 English questions. The metric was Recall@5. Aurora achieved 72.0% Recall@5 on Dataset River v1. There was no reranker. Measurements were made on 2025-03-01 using an eight-core CPU.

## Latency
The median retrieval latency was 18 ms per query, excluding document indexing. The corpus contained 10,000 passages. No generation model was evaluated in this experiment.
