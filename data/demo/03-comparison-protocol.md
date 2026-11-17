# Retrieval comparison protocol
This is a synthetic teaching document.

## Required controls
A direct accuracy comparison requires the same dataset version, question split, corpus, relevance labels and metric cutoff. Recall@5 and Recall@10 measure different operating points. A higher Recall@10 on a different dataset does not establish a better retrieval method. A comparison should also state whether a reranker is used.

## Runtime controls
Latency comparisons must use the same hardware, corpus size, batch size and timing boundary. Indexing cost should be reported separately. These controls have not yet been applied jointly to Aurora and Boreal. A controlled head-to-head evaluation is still required.
