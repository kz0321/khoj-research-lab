"""Measure scoped document reads against the previous whole-collection scan.

Uses synthetic passages and vectors; does not load a model or make network calls.
Both paths must return identical evidence IDs before their timings are accepted.
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.store import Store


def benchmark(documents=500, repeats=30):
    if documents < 2 or repeats < 1:
        raise ValueError("Use at least two documents and one repetition")
    with tempfile.TemporaryDirectory(prefix="khoj-read-bench-") as directory:
        store = Store(Path(directory) / "benchmark.sqlite3")
        store.create_collection("Synthetic benchmark", "benchmark")
        chunks = [{"text": f"Synthetic passage {i}. " * 12,
                   "location": {"start_line": i + 1}} for i in range(8)]
        vectors = np.ones((8, 384), dtype=np.float32)
        for index in range(documents):
            store.save_document("benchmark", {"id": str(index), "title": f"Document {index}",
                "text": "\n".join(c["text"] for c in chunks)}, chunks, vectors)
        target = str(documents // 2)

        def whole_collection():
            return [r for r in store.chunks("benchmark") if r["source_id"] == target or r["title"] == target]

        def scoped_read():
            return store.document_chunks("benchmark", target, match_title=True)

        readers = {"whole_collection": whole_collection, "scoped_read": scoped_read}
        expected = [r["id"] for r in whole_collection()]
        samples = {name: [] for name in readers}
        for reader in readers.values():
            assert [r["id"] for r in reader()] == expected
        for index in range(repeats):
            order = list(readers) if index % 2 == 0 else list(reversed(readers))
            for name in order:
                start = time.perf_counter()
                rows = readers[name]()
                samples[name].append((time.perf_counter() - start) * 1000)
                assert [r["id"] for r in rows] == expected
        medians = {name: statistics.median(values) for name, values in samples.items()}
        return {"python": platform.python_version(), "platform": platform.platform(),
                "documents": documents, "passages": documents * 8, "vector_dimensions": 384,
                "repeats_per_path": repeats, "returned_passages": len(expected),
                "identical_evidence_ids": True, "median_ms": medians,
                "speedup": medians["whole_collection"] / medians["scoped_read"],
                "samples_ms": samples,
                "scope": "Warm synthetic SQLite document lookup, not model generation or retrieval quality."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=int, default=500)
    parser.add_argument("--repeats", type=int, default=30)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = benchmark(args.documents, args.repeats)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
