# Comparing collection retrieval modes

[简体中文](RETRIEVAL.zh-CN.md)

## Developer handoff: what changed from `e9978ae`

**Keep both retrieval paths when refactoring.** The original behavior is still available as the default, `baseline`, so teammates can reproduce earlier rankings. The validated InstaBox deployment explicitly uses `enhanced`. To reproduce the old behavior, set `RETRIEVAL_MODE=baseline` in the server environment or project `.env`, then restart. Both retrieval modes work with the existing agent configurations.

| Area | Before this round | Behavior to preserve |
| --- | --- | --- |
| Chinese keyword matching | The legacy tokenizer treated `香港AI2026` as one token, `香港ai2026`. A BM25 query for `香港` alone could miss that passage. | In enhanced mode, both indexing and querying produce Han characters and adjacent pairs, so `香港` matches and `ai2026` remains searchable. Rebuild the BM25 index when the tokenizer changes. |
| Candidate ranking | Dense and BM25 results were fused by reciprocal rank. The first six went directly to the agent by default. | Keep a bounded candidate pool through the CPU reranker (default 24), then select up to six results. Truncating to six immediately after fusion would prevent the reranker from promoting a lower candidate. Keep the original fused `score` and the enhanced `rerank_score` distinct. |
| Evidence and citations | Identical passages with different chunk IDs could occupy several result slots. Selection followed fused rank regardless of source. | Deduplicate by ID or whitespace-normalized text. Prefer a new source only for a close match with a positive lexical score. Two different facts from one document can both be necessary. Preserve the original chunk ID, text and location for each citation. |
| Reproducible comparisons | There was one retrieval path. The saved runtime configuration recorded the embedding model and limits without a separate retrieval configuration. | Expose and record the active retrieval settings in service status and research results. Keep the evaluation runner's configuration check so a run cannot resume in the same output directory after retrieval settings change. |

When reviewing changes to [the search pipeline](../app/retrieval.py) or [the reranker and evidence selector](../app/reranking.py), check both paths on the server. The [retrieval regression tests](../tests/test_retrieval.py) cover legacy scores, tie order and duplicates as well as enhanced ranking, deduplication and citation identity. Keep the cases for both modes when updating these tests.

## Enhanced mode in detail

1. **Token matching.** The new tokenizer indexes each Han character and each
   overlapping pair within a Han run. For example, a search for 香港 can match
   介紹香港 even without spaces. Latin words, numbers and identifiers such as
   GPT_4 retain their word boundaries. Each mode builds its own in-memory BM25
   index from stored passages. Document replacement invalidates that collection's
   index. Switching modes reuses the same stored dense vectors.
2. **Passage ranking.** After reciprocal rank fusion, the enhanced path examines
   up to `RETRIEVAL_CANDIDATES` passages (default 24, range 6–100). A CPU scorer
   compares the first 512 query characters with up to 1,000 passage characters
   and 150 title characters. Its lexical score combines IDF-weighted query term
   coverage in the passage (65%), adjacent query pair coverage (25%) and title
   coverage (10%). IDF weights have a positive floor. A single-term query uses
   passage coverage for the adjacent-pair component. The final score combines
   70% lexical score with a 30% prior that decreases with the fused rank.
   The scorer uses the existing dependencies and runs synchronously on the
   candidates. A scoring exception appears as a failed tool attempt in the trace.
3. **Evidence selection.** Keep the highest-ranked instance of a chunk ID or
   whitespace-normalized passage. Case, punctuation and digits remain significant.
   When the next passage comes from an already represented source, prefer an
   unseen source only if it has a positive lexical score and falls within
   `RETRIEVAL_DIVERSITY_MARGIN` of that passage's rerank score (default 0.04,
   range 0–0.1). Zero disables the source preference. Complementary passages
   from the same source remain eligible. The returned rows retain their original
   chunk IDs, source IDs, text and citation locations. Deduplication can yield
   fewer than six rows.

Check `/api/status` for the active configuration. Each research result records
the retrieval settings. File search attempts record the number of rows passed
to the scorer (the number returned for the baseline), the scorer and selection
time in `rerank_ms`, and the whole tool time in `elapsed_ms`. The evidence field
`score` is the original fused score. `semantic_score` is dense similarity.
Enhanced evidence also includes `lexical_score` and the combined `rerank_score`
before source selection.

## Server verification

Run from a source checkout on the target server with the project dependencies
and pytest installed. Record the commit or working-tree patch, CPU, memory and
embedding model with the results.

```sh
python -m pytest -q tests/test_retrieval.py tests/test_agent.py tests/test_evaluation.py
python -m eval.compare_retrieval --output outputs/retrieval-dev-01
```

The second command embeds the fixed development corpus once, warms both retrieval
indexes and alternates measurement order across questions. It requires access to
the configured embedding model. Both modes share vectors, labels and top-k. The
new output directory contains the SQLite corpus and `comparison.json`, including
the fixture hash, configuration, ranked chunk IDs and per-question metrics.
Recall@6 counts labeled source and sentence pairs. Mean reciprocal rank uses the
first labeled hit within the first six rows. Relevant-source coverage counts
gold sources with at least one retrieved gold sentence. Duplicate fraction uses
the whitespace normalization described above. Latency measures warm search.

The six author-labeled questions in `eval/retrieval-dev.json` exercise Chinese,
English, mixed input and two-document comparisons. They support development
diagnostics. For acceptance, freeze the settings, supply independently labeled
questions in the same format with `--fixture`, and use a fresh output directory.
Review per-language results, multi-document results and individual regressions.
The default dense model was trained for English. Chinese keyword matches alone
provide limited evidence about semantic retrieval quality.

For a separate end-to-end comparison, configure the generation API on the server.
Start the application in baseline mode and run the first command below. Restart
in enhanced mode and run the second with the same generation settings and
collection. Inspect the actual cited passage, answer and token usage for each
question. Use new output directories for subsequent experiments.

```sh
python -m eval.run --api http://127.0.0.1:3000 --dataset hotpotqa --split dev --limit 4 --modes single_rag --output outputs/e2e-baseline-01
python -m eval.run --api http://127.0.0.1:3000 --dataset hotpotqa --split dev --limit 4 --modes single_rag --output outputs/e2e-enhanced-01
```

These examples use the InstaBox port. For other deployments, supply the address
of the running service.

## InstaBox development run, 2026-11-18

The server operator reported a successful archive checksum check and a healthy
service on `127.0.0.1:3000`. The [pytest log](validation/retrieval-dev-20261118/pytest.log)
records `144 passed in 1.34s`.
The deployed archive had SHA-256
`4e157cb4b0439fcbd4d49d118166b9573dc99c84fb6a483586012aa2c246e662`.
The service returned the following retrieval configuration from `/api/status`.

```json
{"mode":"enhanced","tokenizer":"han-unigram-bigram-v1","reranker":"lexical-coverage-order-v1","candidates":24,"diversity_margin":0.04}
```

The table reports the all-question means from the [original comparison file](validation/retrieval-dev-20261118/comparison.json).
It contains two runs per question (one per mode) for six development questions.
The recorded fixture hash matches the bundled fixture, and both modes used
`BAAI/bge-small-en-v1.5`. The archived files match the SHA-256 digests
calculated on the server in `/data/home/khoj-retrieval-kflURZ`.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| pytest.log | 180 | `8ad68191b30418d7c6157fd3767da8ddf699741383e6708c802465765326fbf9` |
| comparison.json | 12,468 | `7ba07fa595314ed4426505d682c71f792e93ae36d809007738c53c0607cc6c31` |

| Metric | Baseline | Enhanced |
| --- | ---: | ---: |
| Recall@6 | 91.67% | 100% |
| MRR@6 | 0.5694 | 1.0000 |
| Relevant-source coverage | 91.67% | 100% |
| Duplicate fraction | 5.56% | 0% |
| Mean warm search time | 3.95 ms | 4.18 ms |

Each enhanced search placed a labeled passage first and returned all the
labeled evidence within six results. The corpus contains only 14 short
passages, so all fit within the 24-candidate budget. Retrieval under a
binding candidate limit, latency on larger collections and the quality of
generated answers require separate measurements.
