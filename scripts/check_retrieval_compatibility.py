"""Compare current retrieval with a local Git revision using real shared embeddings.

Only the historical retriever is loaded; storage and the embedding model are
shared. This is a ranking regression check on the development fixture, not an
independent benchmark or an end-to-end LLM evaluation.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import retrieval
from app.config import EMBEDDING_MODEL, RETRIEVAL
from app.store import Store


def compare(reference):
    source = subprocess.check_output(["git", "show", f"{reference}:app/retrieval.py"], cwd=ROOT)
    fixture = json.loads((ROOT / "eval/retrieval-dev.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="khoj-compat-") as directory:
        path = Path(directory)
        historical_file = path / "historical_retrieval.py"
        historical_file.write_bytes(source)
        spec = importlib.util.spec_from_file_location("app._historical_retrieval", historical_file)
        historical = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(historical)
        historical.embed = retrieval.embed
        store = Store(path / "corpus.sqlite3")
        cid = store.create_collection("Compatibility fixture", "compatibility")
        writer = retrieval.Retriever(store)
        for document in fixture["documents"]:
            writer.ingest(cid, dict(document, text="\n".join(document["sentences"])))
        comparisons = []
        for mode in ("baseline", "enhanced"):
            settings = replace(RETRIEVAL, mode=mode)
            old, current = historical.Retriever(store, settings), retrieval.Retriever(store, settings)
            for question in fixture["questions"]:
                before = old.search(cid, question["query"])
                after = current.search(cid, question["query"])
                comparisons.append({"mode": mode, "question": question["id"],
                    "identical_rows_scores_and_locations": before == after,
                    "hits": [row["id"] for row in after]})
    return {"reference": reference, "embedding_model": EMBEDDING_MODEL,
            "comparisons": comparisons, "passed": all(c["identical_rows_scores_and_locations"] for c in comparisons),
            "scope": "Six existing development questions in each of two modes; no LLM calls."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, help="Local trusted Git revision to compare")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.reference)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "comparisons": len(result["comparisons"]),
                      "output": str(args.output)}, indent=2))
    raise SystemExit(0 if result["passed"] else 1)
