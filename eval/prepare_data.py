"""Download and freeze the proposal's FRAMES and HotpotQA subsets.

python -m eval.prepare_data --dataset all
No LLM, evaluator labels, or live web calls are used by the application here.
"""
from __future__ import annotations

import argparse
import ast
import concurrent.futures
import csv
import hashlib
import io
import json
import random
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SEED = 20261116
USER_AGENT = "Group30-EvidenceResearch/1.0 (educational dataset preparation)"


def digest(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")


def fetch(url: str, cache: Path) -> bytes:
    if cache.exists():
        return cache.read_bytes()
    cache.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(2):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read()
            cache.write_bytes(raw)
            return raw
        except Exception:
            if attempt:
                raise
            time.sleep(1)
    raise RuntimeError("unreachable")


def hf_revision(dataset: str) -> str:
    url = "https://huggingface.co/api/datasets/" + dataset
    info = json.loads(fetch(url, DATA / "cache" / (dataset.replace("/", "--") + "--metadata.json")))
    return info["sha"]


def hf_rows(dataset: str, config: str, split: str, offset: int, length: int):
    query = urllib.parse.urlencode(dict(dataset=dataset, config=config, split=split, offset=offset, length=length))
    name = f"{dataset.replace('/', '--')}--{config}--{split}--{offset}--{length}.json"
    payload = json.loads(fetch("https://datasets-server.huggingface.co/rows?" + query, DATA / "cache" / name))
    rows = payload["rows"]
    if any(row.get("truncated_cells") for row in rows):
        raise ValueError(f"Dataset server truncated cells for {name}; do not evaluate incomplete evidence")
    return [row["row"] for row in rows]


def balanced_sample(rows: list[dict], count: int, rng: random.Random, field: str) -> list[dict]:
    """Round-robin over complete reasoning/type labels, then shuffle within split."""
    groups = defaultdict(list)
    for row in rows:
        groups[row[field]].append(row)
    for group in groups.values():
        rng.shuffle(group)
    keys = sorted(groups)
    rng.shuffle(keys)
    selected = []
    while len(selected) < count:
        progressed = False
        for key in keys:
            if groups[key] and len(selected) < count:
                selected.append(groups[key].pop())
                progressed = True
        if not progressed:
            raise ValueError("Not enough unique examples")
    rng.shuffle(selected)
    return selected


def prepare_frames(seed: int = SEED) -> dict:
    dataset = "google/frames-benchmark"
    revision = hf_revision(dataset)
    source_url = f"https://huggingface.co/datasets/{dataset}/resolve/{revision}/test.tsv"
    raw = fetch(source_url, DATA / "cache" / "frames-test.tsv")
    fetch(f"https://huggingface.co/datasets/{dataset}/raw/{revision}/README.md", DATA / "licenses" / "frames-dataset-card.md")
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8")), delimiter="\t"))
    unique = {" ".join(row["Prompt"].split()).lower(): row for row in rows}
    rng = random.Random(seed)
    dev = balanced_sample(list(unique.values()), 20, rng, "reasoning_types")
    remaining = [row for row in unique.values() if row not in dev]
    test = balanced_sample(remaining, 100, rng, "reasoning_types")
    selected = [("dev", row) for row in dev] + [("test", row) for row in test]

    snapshot_dataset = "parasail-ai/frames-benchmark-wikipedia"
    snapshot_revision = hf_revision(snapshot_dataset)
    fetch(f"https://huggingface.co/datasets/{snapshot_dataset}/raw/{snapshot_revision}/README.md", DATA / "licenses" / "frames-wikipedia-snapshot-card.md")
    # Pin the compact 33 MB parquet rather than making 26 unpinned API calls.
    # pyarrow is only required for preparation; the app reads the resulting JSONL.
    try:
        import pyarrow.parquet as pq
    except ImportError as error:
        raise RuntimeError("FRAMES preparation needs the optional pyarrow package: python -m pip install pyarrow==22.0.0") from error
    parquet_path = DATA / "cache" / "frames-wikipedia-oct2024.parquet"
    parquet_raw = fetch(f"https://huggingface.co/datasets/{snapshot_dataset}/resolve/{snapshot_revision}/data/train-00000-of-00001.parquet", parquet_path)
    snapshots = pq.read_table(parquet_path).to_pylist()
    selected_ids = {int(row[""]) for _, row in selected}
    relevant = [row for row in snapshots if selected_ids.intersection(row["frames_prompt_id"])]
    distractor_pool = [row for row in snapshots if not selected_ids.intersection(row["frames_prompt_id"])]
    distractors = rng.sample(distractor_pool, min(20, len(distractor_pool)))
    docs, source_map = [], defaultdict(list)
    for row in relevant + distractors:
        text = row["text"]
        doc_id = "frames-" + digest(row["link"] + "\n" + text)[:20]
        docs.append({
            "id": doc_id, "title": row["title"].replace("_", " "), "text": text,
            "url": row["link"], "sha256": digest(text), "license": "CC-BY-SA-3.0/GFDL (snapshot card)",
            "source_dataset": snapshot_dataset, "source_revision": snapshot_revision,
            "snapshot_period": "2024-10 (publisher statement; individual page dates unavailable)",
        })
        for prompt_id in row["frames_prompt_id"]:
            source_map[int(prompt_id)].append(doc_id)
    tasks = []
    for split, row in selected:
        prompt_id = int(row[""])
        urls = ast.literal_eval(row["wiki_links"])
        tasks.append({
            "id": f"frames-{prompt_id}", "dataset": "frames", "split": split,
            "source_split": "test", "source_row": prompt_id, "question": row["Prompt"],
            "answer": row["Answer"], "reasoning_types": row["reasoning_types"].split(" | "),
            "collection_id": "frames-frozen", "gold_source_urls": urls,
            "gold_document_ids": source_map[prompt_id], "temporal_audit": "pending_human_review",
            "answerable": None, "source_revision": revision,
        })
    write_jsonl(DATA / "corpus" / "frames-frozen" / "docs.jsonl", docs)
    write_jsonl(DATA / "evaluation" / "frames-dev.jsonl", [x for x in tasks if x["split"] == "dev"])
    write_jsonl(DATA / "evaluation" / "frames-test.jsonl", [x for x in tasks if x["split"] == "test"])
    audit = [{"task_id": t["id"], "question": t["question"], "reference_answer": t["answer"],
              "gold_source_urls": t["gold_source_urls"], "mapped_document_count": len(t["gold_document_ids"]),
              "status": "pending", "rater": "", "notes": "Confirm required facts and temporal constraints against saved October-2024 sources; do not infer correctness from answer string presence."} for t in tasks]
    write_jsonl(DATA / "evaluation" / "frames-temporal-audit.jsonl", audit)
    manifest = {
        "dataset": dataset, "revision": revision, "seed": seed, "source_sha256": digest(raw),
        "source_rows": len(rows), "unique_questions": len(unique), "dev": 20, "test": 100,
        "sampling": "fixed-seed round-robin over complete reasoning label combinations; dev removed before test sampling",
        "reasoning_type_counts": {split: dict(Counter(tag for t in tasks if t["split"] == split for tag in t["reasoning_types"])) for split in ["dev", "test"]},
        "snapshot_dataset": snapshot_dataset, "snapshot_revision": snapshot_revision,
        "snapshot_parquet_sha256": digest(parquet_raw),
        "snapshot_source_count": len(snapshots), "selected_corpus_documents": len(docs), "distractor_documents": len(distractors),
        "corpus_sha256": digest((DATA / "corpus" / "frames-frozen" / "docs.jsonl").read_bytes()),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "status": "prepared_not_human_audited_not_benchmark_evaluated",
        "limitations": ["Third-party October 2024 snapshots are not necessarily the question's original as-of date.",
                       "Question-to-source mappings and answers are outside the searchable corpus.",
                       "Source annotations identify documents, not complete gold supporting spans.",
                       "The source parquet is pinned to the recorded publisher revision and SHA256."],
    }
    write_json(DATA / "manifests" / "frames.json", manifest)
    return manifest


def prepare_hotpot(seed: int = SEED) -> dict:
    dataset = "hotpotqa/hotpot_qa"
    revision = hf_revision(dataset)
    fetch(f"https://huggingface.co/datasets/{dataset}/raw/{revision}/README.md", DATA / "licenses" / "hotpotqa-dataset-card.md")
    rng = random.Random(seed)
    tasks = []
    manifests = []
    seen_questions = set()
    excluded_structure = []
    for source_split, target_split, total, count in [("train", "dev", 90447, 20), ("validation", "test", 7405, 40)]:
        # Uniform sample without replacement. Dataset order is not used as a pseudo-random sample.
        offsets = rng.sample(range(total), count + 200)
        selected_rows = []
        for start in range(0, len(offsets), 10):
            requested = offsets[start:start+10]
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
                fetched = list(pool.map(lambda offset: hf_rows(dataset, "distractor", source_split, offset, 1)[0], requested))
            for offset, row in zip(requested, fetched):
                if len(row["context"]["title"]) != 10:
                    excluded_structure.append({"source_split":source_split,"source_row":offset,"reason":"not_ten_paragraphs","paragraphs":len(row["context"]["title"])})
                    continue
                normalized_question = " ".join(row["question"].split()).lower()
                if normalized_question not in seen_questions:
                    seen_questions.add(normalized_question)
                    selected_rows.append((offset, row))
                if len(selected_rows) == count:
                    break
            if len(selected_rows) == count:
                break
        if len(selected_rows) != count:
            raise ValueError("Insufficient unique HotpotQA rows")
        for offset, row in selected_rows:
            task_id = "hotpot-" + row["id"]
            docs = []
            context = row["context"]
            for title, sentences in zip(context["title"], context["sentences"]):
                text = "\n".join(sentences)
                docs.append({
                    "id": "hotpot-doc-" + digest(title + "\n" + text)[:20], "title": title,
                    "text": text, "sentences": [{"id": i, "text": sentence} for i, sentence in enumerate(sentences)],
                    "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_")),
                    "sha256": digest(text), "license": "CC-BY-SA-4.0 (HotpotQA dataset card)",
                    "source_dataset": dataset, "source_revision": revision,
                    "source_split": source_split,
                })
            if len(docs) != 10:
                raise ValueError(f"Expected ten distractor paragraphs for {task_id}, got {len(docs)}")
            gold = list(map(list, zip(row["supporting_facts"]["title"], row["supporting_facts"]["sent_id"])))
            task = {
                "id": task_id, "original_id": row["id"], "dataset": "hotpotqa", "split": target_split,
                "source_split": source_split, "source_row": offset, "question": row["question"],
                "answer": row["answer"], "type": row["type"], "level": row["level"],
                "supporting_facts": gold, "collection_id": task_id,
                "answerable": True, "source_revision": revision,
            }
            path = DATA / "corpus" / task_id / "docs.jsonl"
            write_jsonl(path, docs)
            tasks.append(task)
            manifests.append({"collection_id": task_id, "documents": len(docs), "sha256": digest(path.read_bytes()), "source_split": source_split, "source_row": offset})
        if set(x["type"] for _, x in selected_rows) != {"bridge", "comparison"}:
            raise ValueError(f"Sample {target_split} lacks one question type; choose a new predeclared seed before testing")
    for split in ["dev", "test"]:
        write_jsonl(DATA / "evaluation" / f"hotpotqa-{split}.jsonl", [x for x in tasks if x["split"] == split])
    # All scenarios are chosen before model runs; insufficient variants still need two human raters.
    candidates = sorted((t for t in tasks if t["split"] == "test"), key=lambda x: x["id"])
    selected_perturbations = random.Random(seed + 17).sample(candidates, 8)
    perturbations = [{"task_id": task["id"], "scenario": scenario, "affected_tool_attempt": 1,
                      "sufficiency_audit": "pending_two_raters" if scenario == "withhold_support" else "not_applicable"}
                     for task in selected_perturbations for scenario in ["timeout", "empty", "irrelevant", "withhold_support"]]
    write_jsonl(DATA / "evaluation" / "hotpotqa-perturbations.jsonl", perturbations)
    manifest = {
        "dataset": dataset, "revision": revision, "configuration": "distractor", "seed": seed,
        "dev": 20, "test": 40, "sampling": "uniform random row indices without replacement within official train/validation; retain exactly-ten-paragraph contexts and remove duplicate questions before model runs",
        "excluded_structure": excluded_structure,
        "test_description": "40 held-out items from the publicly released official development (HF validation) split; not an official hidden-test submission",
        "type_counts": {split: dict(Counter(t["type"] for t in tasks if t["split"] == split)) for split in ["dev", "test"]},
        "collections": manifests, "documents": sum(x["documents"] for x in manifests),
        "created_utc": datetime.now(timezone.utc).isoformat(), "perturbation_task_count": 8,
        "status": "prepared_not_benchmark_evaluated",
        "limitations": ["Dataset-server responses are saved as the source-of-truth snapshot; its API is not revision-pinned.",
                       "Withholding annotated sentences is not proof of insufficiency; two humans must audit other accessible passages."],
    }
    write_json(DATA / "manifests" / "hotpotqa.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=["all", "frames", "hotpotqa"], default="all")
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    for name, fn in [("hotpotqa", prepare_hotpot), ("frames", prepare_frames)]:
        if args.dataset in [name, "all"]:
            result = fn(args.seed)
            print(json.dumps({"dataset": name, "dev": result["dev"], "test": result["test"], "status": result["status"]}))


if __name__ == "__main__":
    main()
