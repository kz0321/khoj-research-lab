"""Compare both retrieval modes against passage labels using the same stored vectors."""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from statistics import fmean
import time

from app.config import EMBEDDING_MODEL, RETRIEVAL
from app.retrieval import Retriever
from app.store import Store


def score(rows, labels):
    gold = set(map(tuple, labels))
    if not gold:
        raise ValueError("Each question needs at least one relevant source and sentence")
    found = set()
    first = 0
    texts = set()
    for rank, row in enumerate(rows, start=1):
        hits = {(row["source_id"], sid) for sid in row["location"]["sentence_ids"]} & gold
        if hits and not first:
            first = rank
        found.update(hits)
        texts.add(" ".join(row["text"].split()))
    return {
        "recall_at_6": len(found) / len(gold),
        "reciprocal_rank_at_6": 1 / first if first else 0,
        "relevant_source_coverage": len({s for s, _ in found}) / len({s for s, _ in gold}),
        "duplicate_fraction": (len(rows) - len(texts)) / len(rows) if rows else 0,
    }


def compare(fixture_path, output):
    raw = fixture_path.read_bytes()
    fixture = json.loads(raw)
    output.mkdir(parents=True, exist_ok=False)
    store = Store(output / "corpus.sqlite3")
    cid = store.create_collection("Retrieval comparison", "retrieval-dev")
    retrievers = {mode: Retriever(store, replace(RETRIEVAL, mode=mode)) for mode in ("baseline", "enhanced")}
    available = set()
    for doc in fixture["documents"]:
        retrievers["baseline"].ingest(cid, dict(doc, text="\n".join(doc["sentences"])))
    for row in store.chunks(cid):
        available.update((row["source_id"], sid) for sid in row["location"]["sentence_ids"])
    for question in fixture["questions"]:
        if not question["relevant"] or not set(map(tuple, question["relevant"])) <= available:
            raise ValueError(f"Invalid passage labels for {question['id']}")

    records = []
    groups = defaultdict(list)
    for retriever in retrievers.values():
        retriever.search(cid, "warm up")  # Build both BM25 indexes outside the timed runs.
    for i, question in enumerate(fixture["questions"]):
        modes = list(retrievers)
        if i % 2:
            modes.reverse()
        for mode in modes:
            trace = {}
            started = time.perf_counter()
            rows = retrievers[mode].search(cid, question["query"], 6, diagnostics=trace)
            duration = (time.perf_counter() - started) * 1000
            metrics = dict(score(rows, question["relevant"]), latency_ms=duration)
            records.append({"question": question["id"], "mode": mode, "metrics": metrics,
                            "retrieval": trace, "hits": [r["id"] for r in rows]})
            groups[mode, "all"].append(metrics)
            groups[mode, question["language"]].append(metrics)
            if len({s for s, _ in question["relevant"]}) > 1:
                groups[mode, "multi_document"].append(metrics)
    summary = [{"mode": mode, "group": group, "questions": len(values),
                "mean": {key: fmean(row[key] for row in values) for key in values[0]}}
               for (mode, group), values in groups.items()]
    result = {"fixture_sha256": hashlib.sha256(raw).hexdigest(), "embedding_model": EMBEDDING_MODEL,
              "settings": {k: v.settings.describe() for k, v in retrievers.items()},
              "summary": summary, "records": records}
    (output / "comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=Path(__file__).with_name("retrieval-dev.json"))
    parser.add_argument("--output", type=Path, required=True, help="New directory for the corpus and scores")
    args = parser.parse_args()
    compare(args.fixture, args.output)
