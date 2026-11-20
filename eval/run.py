"""Resumable fixed-corpus evaluation against the local application.

Example: python -m eval.run --dataset hotpotqa --split dev --limit 4
Gold answers are read only by this evaluator. They are never posted to the app.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from eval.metrics import paired_bootstrap, percentile, task_score
from eval.perturbations import tool_perturbation, withhold_support
from eval.prepare_data import ROOT, DATA, SEED, write_json

MODES = ["no_tools", "single_rag", "multi_step", "verified", "verified_no_repair"]


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def request_json(api: str, path: str, payload=None, timeout=120):
    request = urllib.request.Request(api.rstrip("/")+path,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"Content-Type":"application/json"}, method="POST" if payload is not None else "GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8",errors="replace")[:2000]
        raise RuntimeError(f"HTTP {error.code} {path}: {body}") from error


def public_document(doc: dict) -> dict:
    """Positive allowlist: no question/source mapping or reference label can leak."""
    return {"id": doc["id"], "title": doc["title"], "text": doc["text"],
            "sentences": doc.get("sentences"), "url": doc.get("url"),
            "metadata": {key:doc[key] for key in ["sha256","license","source_dataset","source_revision","source_split","snapshot_period"] if key in doc}}


def import_collection(api: str, task: dict, scenario: str) -> str:
    collection = task["collection_id"]
    docs = read_jsonl(DATA / "corpus" / collection / "docs.jsonl")
    if scenario == "withhold_support":
        if task["dataset"] != "hotpotqa":
            raise ValueError("Supporting-sentence withholding is defined for HotpotQA only")
        docs = withhold_support(docs, task["supporting_facts"])
        collection += "-withheld"
    request_json(api, "/api/collections", {"id": collection, "name": collection})
    # Stable IDs allow idempotent ingestion; split large FRAMES corpus into batches.
    for offset in range(0, len(docs), 20):
        imported = request_json(api, f"/api/collections/{collection}/import", {"documents":[public_document(d) for d in docs[offset:offset+20]]}, timeout=300)
        if imported.get("errors"):
            raise RuntimeError("Corpus import was incomplete; refusing unequal evidence access: " + json.dumps(imported["errors"]))
    collection_record=next((item for item in request_json(api,"/api/collections")["collections"] if item["id"]==collection),None)
    if collection_record is None or collection_record["documents"]!=len(docs):
        raise RuntimeError("Frozen collection contains missing or extra documents; use a clean dataset collection before comparing systems")
    return collection


def execute(api: str, task: dict, mode: str, collection: str, scenario: str, timeout: float) -> dict:
    started = time.monotonic()
    payload = {"question":task["question"],"mode":mode,"collection_id":collection,"allow_web":False}
    perturbation = tool_perturbation(scenario)
    if perturbation:
        payload["perturbation"] = perturbation
    submitted = request_json(api, "/api/research", payload)
    run_id = submitted["id"]
    while time.monotonic() - started < timeout:
        response = request_json(api, f"/api/runs/{run_id}", timeout=60)
        if response.get("status") not in {"queued","running","pending"}:
            response["client_elapsed_seconds"] = time.monotonic()-started
            return response
        time.sleep(1)
    return {"id":run_id,"status":"client_timeout","error":"Evaluation polling time limit exceeded; inspect server run before retrying", "client_elapsed_seconds":time.monotonic()-started}


def summarize(records: list[dict]) -> dict:
    all_attempts=records
    latest={r.get("key",f"{r['task_id']}:{r['mode']}:{r['scenario']}:{r.get('repeat',0)}"):r for r in records}
    records=list(latest.values())
    groups = defaultdict(list)
    for row in records:
        groups[(row["dataset"],row["split"],row["scenario"],row["mode"])].append(row)
    summaries = []
    for (dataset,split,scenario,mode), rows in sorted(groups.items()):
        scores = [r["scores"] for r in rows]
        history=[r["scores"] for r in all_attempts if (r["dataset"],r["split"],r["scenario"],r["mode"])==(dataset,split,scenario,mode)]
        numerical = ["answer_em","answer_f1","supporting_em","supporting_f1"]
        group = {"dataset":dataset,"split":split,"scenario":scenario,"mode":mode,"attempted_runs":len(rows),
                 "unique_tasks":len({r["task_id"] for r in rows}),"failed_runs":sum(s["failed"] for s in scores),
                 "recorded_attempts_including_explicit_reruns":len(history),
                 "failed_attempts_including_explicit_reruns":sum(s["failed"] for s in history),
                 "answer_rate":statistics.fmean(float(s["answered"]) for s in scores),
                 "actual_repeats_per_task":dict(__import__('collections').Counter(r["task_id"] for r in rows))}
        for metric in numerical:
            values = [s[metric] for s in scores if metric in s]
            group[metric] = statistics.fmean(values) if values else None
        times = [s["elapsed_seconds"] for s in scores if s.get("elapsed_seconds") is not None]
        group.update({"latency_median_seconds":statistics.median(times) if times else None,
                      "latency_p95_seconds":percentile(times,.95),
                      "input_tokens_total":sum((s.get("usage") or {}).get("input_tokens",0) for s in history),
                      "output_tokens_total":sum((s.get("usage") or {}).get("output_tokens",0) for s in history),
                      "tool_calls_total":sum(s.get("tool_calls",0) for s in history),
                      "model_calls_total":sum(s.get("model_calls",0) for s in history),
                      "citation_support_precision":None,"citation_coverage":None,"unsupported_claim_rate":None,
                      "task_success":None,"correct_abstention_rate":None,"recovery_rate":None,
                      "human_judging_status":"not_scored_until_blinded_two_rater_annotations_are_resolved"})
        token_totals = [(s.get("usage") or {}).get("input_tokens",0)+(s.get("usage") or {}).get("output_tokens",0) for s in scores]
        group["tokens_median"] = statistics.median(token_totals)
        costs=[(s.get("usage") or {}).get("estimated_cost_usd") for s in history]
        group["estimated_cost_usd_total"] = sum(costs) if all(x is not None for x in costs) else None
        group["unknown_usage_attempts"] = sum((s.get("usage") or {}).get("unknown_usage_attempts",0) for s in history)
        group["pricing_dates"] = sorted({(s.get("usage") or {}).get("pricing_date") for s in history if (s.get("usage") or {}).get("pricing_date")})
        summaries.append(group)
    comparisons = []
    for dataset,split,scenario in sorted({(r["dataset"],r["split"],r["scenario"]) for r in records}):
        for metric in ["answer_em","answer_f1","supporting_f1"]:
            by_mode = {}
            for mode in ["multi_step","verified"]:
                values = defaultdict(list)
                for row in records:
                    if (row["dataset"],row["split"],row["scenario"],row["mode"]) == (dataset,split,scenario,mode) and metric in row["scores"]:
                        values[row["task_id"]].append(row["scores"][metric])
                by_mode[mode] = {key:statistics.fmean(value) for key,value in values.items()}
            if all(by_mode.values()):
                comparisons.append({"dataset":dataset,"split":split,"scenario":scenario,"metric":metric,
                                    "contrast":"verified minus multi_step",**paired_bootstrap(by_mode["multi_step"],by_mode["verified"])})
    return {"groups":summaries,"paired_comparisons":comparisons,
            "notice":"Automatic EM/F1 and measured resource use are not human evidence-support judgments. Development pilot results are not held-out benchmark claims. Quality uses the last explicit attempt per task/mode/repeat; total tokens/calls/cost preserve all attempts including reruns."}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api",default="http://127.0.0.1:8778")
    parser.add_argument("--dataset",choices=["hotpotqa","frames"],default="hotpotqa")
    parser.add_argument("--split",choices=["dev","test"],default="dev")
    parser.add_argument("--limit",type=int,default=4,help="0 means all selected items; default is only a development pilot")
    parser.add_argument("--modes",nargs="+",choices=MODES,default=MODES)
    parser.add_argument("--repeats",type=int,default=1)
    parser.add_argument("--scenario",choices=["clean","timeout","empty","irrelevant","withhold_support"],default="clean")
    parser.add_argument("--development-perturbations",action="store_true",help="Diagnostic only: perturb the selected development tasks instead of the preselected held-out robustness subset")
    parser.add_argument("--output",type=Path,default=ROOT/"eval"/"results"/"development-pilot")
    parser.add_argument("--timeout",type=float,default=900)
    parser.add_argument("--allow-unreviewed-frames",action="store_true",help="Diagnostic only; mark results unaudited")
    parser.add_argument("--rerun-failures",action="store_true")
    parser.add_argument("--pause-file",type=Path,default=DATA/"manifests/evaluation.pause",help="If present, stop after the current complete task; remove before resuming")
    args=parser.parse_args()
    if args.repeats<1 or args.limit<0:
        parser.error("repeats >= 1 and limit >= 0 required")
    if args.development_perturbations and (args.split!="dev" or args.dataset!="hotpotqa"):
        parser.error("Development perturbation diagnostics are only defined for HotpotQA development tasks")
    task_file=DATA/"evaluation"/f"{args.dataset}-{args.split}.jsonl"
    tasks=read_jsonl(task_file)
    if args.scenario!="clean" and args.dataset=="hotpotqa" and not args.development_perturbations:
        chosen={x["task_id"] for x in read_jsonl(DATA/"evaluation"/"hotpotqa-perturbations.jsonl") if x["scenario"]==args.scenario}
        tasks=[t for t in tasks if t["id"] in chosen]
    if args.limit:
        tasks=tasks[:args.limit]
    if not tasks:
        parser.error("No tasks match; preselected perturbations are in HotpotQA test split")
    if args.dataset=="frames" and not args.allow_unreviewed_frames:
        audit={x["task_id"]:x for x in read_jsonl(DATA/"evaluation"/"frames-temporal-audit.jsonl")}
        pending=[t["id"] for t in tasks if audit.get(t["id"],{}).get("status")!="approved"]
        if pending:
            parser.error("FRAMES source/temporal audit pending. Complete saved audit first, or explicitly use --allow-unreviewed-frames for diagnostic results only.")
    args.output.mkdir(parents=True,exist_ok=True)
    records_path=args.output/"runs.jsonl"
    records=read_jsonl(records_path) if records_path.exists() else []
    config_path=args.output/"configuration.json"
    config={"dataset":args.dataset,"split":args.split,"selected_task_ids":[t["id"] for t in tasks],"modes":args.modes,
            "repeats":args.repeats,"scenario":args.scenario,"seed":SEED,"api":args.api,
            "development_perturbation_diagnostic":args.development_perturbations,
            "task_file_sha256":hashlib.sha256(task_file.read_bytes()).hexdigest(),
            "dataset_manifest_sha256":hashlib.sha256((DATA/"manifests"/f"{args.dataset}.json").read_bytes()).hexdigest(),
            "agent_source_sha256":hashlib.sha256("\n".join(str(path.relative_to(ROOT))+":"+hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted((ROOT/"app").glob("*.py"))).encode()).hexdigest(),
            "live_web":False,"frames_temporal_review_bypassed":args.allow_unreviewed_frames}
    try:
        health=request_json(args.api,"/api/status")
    except Exception as error:
        health={"unavailable":str(error)}
    if config_path.exists():
        prior=json.loads(config_path.read_text(encoding="utf-8"))
        previous_configuration=dict(prior.get("configuration",{}))
        previous_configuration.setdefault("development_perturbation_diagnostic",False)
        if previous_configuration!=config:
            parser.error("Output directory has a different frozen configuration; choose a new --output directory")
        for key in ["model","embedding_model","retrieval","agent_policy","limits","upstream_commit","thinking","structured_output"]:
            if prior.get("runtime_at_start",{}).get(key)!=health.get(key):
                parser.error(f"Runtime {key} changed since configuration freeze; choose a new --output directory")
    else:
        write_json(config_path,{"configuration":config,"runtime_at_start":health,"created_utc":datetime.now(timezone.utc).isoformat()})
    done={r["key"] for r in records if not args.rerun_failures or not r["scores"]["failed"]}
    imported=set()
    for task in tasks:
        collection=task["collection_id"]+("-withheld" if args.scenario=="withhold_support" else "")
        for repeat in range(args.repeats):
            for mode in args.modes:
                if args.pause_file.exists():
                    print("Paused safely between tasks because the evaluation pause marker exists.",flush=True)
                    return
                key=f"{task['id']}:{mode}:{args.scenario}:{repeat}"
                if key in done:
                    continue
                if collection not in imported and mode!="no_tools":
                    collection=import_collection(args.api,task,args.scenario)
                    imported.add(collection)
                started=time.monotonic()
                try:
                    response=execute(args.api,task,mode,collection,args.scenario,args.timeout)
                except Exception as error:
                    response={"status":"failed","error":str(error),"client_elapsed_seconds":time.monotonic()-started}
                row={"key":key,"task_id":task["id"],"dataset":args.dataset,"split":args.split,"mode":mode,
                     "scenario":args.scenario,"repeat":repeat,"question":task["question"],"reference_answer":task["answer"],
                     "attempt":1+sum(r["key"]==key for r in records),
                     "response":response,"scores":task_score(task,response)}
                records.append(row)
                with records_path.open("a",encoding="utf-8") as stream:
                    stream.write(json.dumps(row,ensure_ascii=False)+"\n")
                write_json(args.output/"summary.json",summarize(records))
                print(json.dumps({"key":key,"status":response.get("status"),"em":row["scores"]["answer_em"],"seconds":row["scores"]["elapsed_seconds"]}),flush=True)
                if response.get("status")=="client_timeout":
                    raise SystemExit("Client stopped after timeout to avoid overlapping unobserved model runs. Inspect server before resuming.")
                if response.get("status")=="failed" and re.search(r"Model HTTP (401|402|403|404)\b",str(response.get("error",""))):
                    raise SystemExit("Stopped after provider authorization/balance/model error. Failure and unknown usage were recorded; configure a working provider before a new run.")
    write_json(args.output/"summary.json",summarize(records))


if __name__=="__main__":
    main()
