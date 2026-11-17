"""Finalize a completed experiment with official scores and integrity checks.

python -m eval.report_results --directory eval/results/hotpot-test-frozen-r1
This reads recorded outputs only; it never calls a model or tunes the application.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import statistics
from collections import Counter
from pathlib import Path

from eval.annotations import export_annotations
from eval.metrics import percentile
from eval.official_hotpot import evaluate
from eval.prepare_data import ROOT,write_json
from eval.run import read_jsonl,summarize


def finalize(directory:Path):
    config=json.loads((directory/"configuration.json").read_text(encoding="utf-8"))
    experiment=config["configuration"]
    records=read_jsonl(directory/"runs.jsonl")
    latest=list({r["key"]:r for r in records}.values())
    expected={(task,mode,repeat) for task in experiment["selected_task_ids"] for mode in experiment["modes"] for repeat in range(experiment["repeats"])}
    actual={(r["task_id"],r["mode"],r["repeat"]) for r in latest}
    if actual!=expected:
        raise ValueError(f"Experiment incomplete: expected{len(expected)} unique runs, have{len(actual)}; missing{len(expected-actual)}, extra{len(actual-expected)}")
    audit={"complete_run_matrix":True,"unique_tasks":len(experiment["selected_task_ids"]),"recorded_runs":len(latest),
           "actual_repeats":experiment["repeats"],"split":experiment["split"],"dataset":experiment["dataset"],
           "scenario":experiment["scenario"],"failures_in_denominator":sum(r["scores"]["failed"] for r in latest),
           "provider_returned_models":[],"live_web_executions":0,"budget_violations":[],"configuration_mismatches":[],
           "human_citation_judgments":"pending","human_task_judgments":"pending"}
    models=set();input_tokens=output_tokens=calls=0;server_ids=set()
    for row in latest:
        response=row["response"];result=response.get("result") or {};run_config=result.get("configuration") or {}
        if response.get("id"):
            if response["id"] in server_ids:raise ValueError("One server run was reused for multiple experimental records")
            server_ids.add(response["id"])
        for key in ["model","embedding_model","limits","upstream_commit"]:
            if key in run_config and run_config[key]!=config["runtime_at_start"].get(key):
                audit["configuration_mismatches"].append({"key":row["key"],"field":key})
        if run_config.get("allow_web"):
            audit["configuration_mismatches"].append({"key":row["key"],"field":"allow_web"})
        for event in result.get("model_calls",[]):
            if event.get("returned_model"):models.add(event["returned_model"])
        for event in result.get("trace",[]):
            if event.get("tool") in {"search_web","read_webpage"} and event.get("status")=="completed":audit["live_web_executions"]+=1
        limits=config["runtime_at_start"].get("limits",{})
        for field,budget_key in [("rounds","decision_rounds"),("tool_calls","tool_calls"),("repair_rounds","repair_rounds")]:
            if result.get(field,0)>limits.get(budget_key,float("inf")):
                audit["budget_violations"].append({"key":row["key"],"field":field,"value":result[field]})
        usage=result.get("usage") or {}
        if usage.get("calls",0)>limits.get("model_calls",float("inf")):
            audit["budget_violations"].append({"key":row["key"],"field":"model_calls","value":usage["calls"]})
        input_tokens+=usage.get("input_tokens",0);output_tokens+=usage.get("output_tokens",0);calls+=usage.get("calls",0)
    current_hash=hashlib.sha256("\n".join(str(p.relative_to(ROOT))+":"+hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/"app").glob("*.py"))).encode()).hexdigest()
    audit.update({"source_hash_unchanged":current_hash==experiment.get("agent_source_sha256"),
                  "provider_returned_models":sorted(models),"model_calls_total_latest_attempts":calls,
                  "input_tokens_total_latest_attempts":input_tokens,"output_tokens_total_latest_attempts":output_tokens})
    audit["protocol_checks_passed"]=(audit["source_hash_unchanged"] and not audit["configuration_mismatches"] and not audit["budget_violations"] and not audit["live_web_executions"])
    summary=summarize(records)
    write_json(directory/"summary.json",summary)
    for group in summary["groups"]:
        selected=[r for r in latest if r["mode"]==group["mode"] and r["scenario"]==group["scenario"]]
        client_times=[r["response"]["client_elapsed_seconds"] for r in selected if r["response"].get("client_elapsed_seconds") is not None]
        overhead=[max(0,r["response"]["client_elapsed_seconds"]-(r["response"].get("result") or {})["elapsed_seconds"]) for r in selected
                  if r["response"].get("client_elapsed_seconds") is not None and (r["response"].get("result") or {}).get("elapsed_seconds") is not None]
        group["client_end_to_end_median_seconds"]=statistics.median(client_times) if client_times else None
        group["client_end_to_end_p95_seconds"]=percentile(client_times,.95)
        group["queue_and_poll_overhead_median_seconds"]=statistics.median(overhead) if overhead else None
        group["latency_definition"]="latency_* is server task execution; client_end_to_end_* additionally includes submission, queue wait, polling and HTTP overhead"
        group["abstained_runs"]=sum(not (r["response"].get("result") or {}).get("answer") and not r["scores"]["failed"] for r in selected)
        group["runs_with_repair"]=sum((r["response"].get("result") or {}).get("repair_rounds",0)>0 for r in selected)
        group["stop_reasons"]=dict(Counter((r["response"].get("result") or {}).get("stop_reason","failure") for r in selected))
    write_json(directory/"summary.json",summary)
    if experiment["dataset"]=="hotpotqa":
        official=[]
        for mode in experiment["modes"]:
            for repeat in range(experiment["repeats"]):
                official.append(evaluate(directory/"runs.jsonl",mode,experiment["split"],repeat,experiment["scenario"],directory/f"official-{mode}-r{repeat}"))
        write_json(directory/"official-all.json",official)
    annotation=export_annotations(directory/"runs.jsonl",directory/"blind")
    audit["blinded_claim_passage_items"]=annotation["items"]
    write_json(directory/"experiment-audit.json",audit)
    fields=["mode","attempted_runs","failed_runs","answer_em","answer_f1","supporting_f1","answer_rate","abstained_runs","runs_with_repair","latency_median_seconds","latency_p95_seconds","client_end_to_end_median_seconds","client_end_to_end_p95_seconds","tokens_median","input_tokens_total","output_tokens_total","tool_calls_total","model_calls_total","estimated_cost_usd_total"]
    with (directory/"results-table.csv").open("w",encoding="utf-8-sig",newline="") as stream:
        writer=csv.DictWriter(stream,fieldnames=fields,extrasaction="ignore");writer.writeheader();writer.writerows(summary["groups"])
    return audit


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--directory",type=Path,required=True)
    args=parser.parse_args();print(json.dumps(finalize(args.directory)))
