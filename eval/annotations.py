"""Export blinded claim-passage pairs and score independently completed labels.

Export: python -m eval.annotations export --runs eval/results/development-pilot/runs.jsonl --output eval/results/blind
Score: python -m eval.annotations score --rater-a A.csv --rater-b B.csv --resolved resolved.csv --output scores.json
Never fill these human judgments using the agent checker itself.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import random
from pathlib import Path

from eval.metrics import cohen_kappa, human_grounding_scores, visible_claims, paired_ratio_bootstrap
from eval.prepare_data import SEED, write_json
from eval.run import read_jsonl

LABELS={"supported","unsupported","contradicted","not_verifiable"}


def export_annotations(runs: Path, output: Path):
    # Re-exporting must not erase human work or attach old labels to a new rerun.
    for name in ["rater-A.csv","rater-B.csv","task-rater-A.csv","task-rater-B.csv"]:
        path=output/name
        if path.exists():
            with path.open(encoding="utf-8-sig",newline="") as stream:
                if any(any(row.get(field,"").strip() for field in ["label","notes","answer_correct","required_claims_supported","evidence_sufficient","abstention_correct","failure_category"]) for row in csv.DictReader(stream)):
                    raise ValueError(f"Existing human annotations in {path}; choose a new output directory to preserve them")
    rows=[]
    key=[]
    task_rows=[]
    task_key=[]
    records=list({record["key"]:record for record in read_jsonl(runs)}.values())
    for record in records:
        response=record["response"]
        result=response.get("result") or {}
        final_claims=visible_claims(result)
        final_evidence_ids={eid for claim in final_claims for eid in claim.get("evidence_ids",[])}
        neutral_report="\n".join([claim["text"]+" "+" ".join("["+eid+"]" for eid in claim.get("evidence_ids",[])) for claim in final_claims])
        neutral_report+="\n\n"+"\n\n".join("["+item["id"]+"] "+item.get("title","")+"\n"+item.get("text","") for item in result.get("evidence",[]) if item["id"] in final_evidence_ids)
        attempt_identity=str(response.get("id") or record.get("attempt",1))
        task_blind_id=hashlib.sha256(("task-blind-v1:"+record["key"]+":"+attempt_identity).encode()).hexdigest()[:20]
        task_rows.append({"item_id":task_blind_id,"question":record["question"],"reference_answer":record.get("reference_answer",""),
                          "answer":result.get("answer",""),"report":neutral_report,
                          "answer_correct":"","required_claims_supported":"","evidence_sufficient":"",
                          "abstention_correct":"","failure_category":"","notes":""})
        task_key.append({"item_id":task_blind_id,"task_id":record["task_id"],"run_id":response.get("id",record["key"]),
                         "mode":record["mode"],"scenario":record["scenario"],"repeat":record["repeat"],
                         "answered":bool(result.get("answer")),"failed":response.get("status")!="completed"})
        evidence={e["id"]:e for e in result.get("evidence",[])}
        for claim in visible_claims(result):
            citations=claim.get("evidence_ids") or [""]
            for citation in citations:
                passage=evidence.get(citation,{})
                identity=record["key"]+":"+attempt_identity+":"+str(claim["id"])+":"+citation
                blind_id=hashlib.sha256(("blind-v1:"+identity).encode()).hexdigest()[:20]
                rows.append({"item_id":blind_id,"question":record["question"],"answer":result.get("answer",""),
                             "claim":claim["text"],"source_title":passage.get("title",""),
                             "source_location":json.dumps(passage.get("location",{}),ensure_ascii=False),
                             "passage":passage.get("text",""),"label":"","notes":""})
                key.append({"item_id":blind_id,"task_id":record["task_id"],"run_id":response.get("id",record["key"]),
                            "claim_id":claim["id"],"evidence_id":citation,"mode":record["mode"],"scenario":record["scenario"],"repeat":record["repeat"]})
    random.Random(SEED).shuffle(rows)
    output.mkdir(parents=True,exist_ok=True)
    fields=["item_id","question","answer","claim","source_title","source_location","passage","label","notes"]
    for name in ["rater-A.csv","rater-B.csv"]:
        with (output/name).open("w",encoding="utf-8-sig",newline="") as stream:
            writer=csv.DictWriter(stream,fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
    write_json(output/"PRIVATE-system-key.json",key)
    random.Random(SEED+1).shuffle(task_rows)
    for name in ["task-rater-A.csv","task-rater-B.csv"]:
        with (output/name).open("w",encoding="utf-8-sig",newline="") as stream:
            fields=["item_id","question","reference_answer","answer","report","answer_correct","required_claims_supported","evidence_sufficient","abstention_correct","failure_category","notes"]
            writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(task_rows)
    write_json(output/"PRIVATE-task-key.json",task_key)
    write_json(output/"instructions.json",{
        "raters":2,"items":len(rows),"blinding":"Keep PRIVATE-system-key.json away from raters; exported rows hide mode, checker status and verifier reasoning.",
        "rubric":{"supported":"The quoted passage supports the entire factual claim including numbers, units, dates and qualifications.",
                  "unsupported":"Missing citation, insufficient passage, missing condition, or inference unsupported by that passage.",
                  "contradicted":"The passage explicitly conflicts with the claim.",
                  "not_verifiable":"Not an externally verifiable factual claim; exclude from factual-claim denominator with recorded rationale."},
        "process":"Raters label independently. Compute agreement before reconciliation. Resolve disagreements into resolved.csv with item_id,label,notes. Separately audit answer equivalence, task success and evidence-insufficient variants.",
        "task_rubric":"Complete citation judging first, then separate task forms. answer_correct: yes/no (semantic equivalents count yes); required_claims_supported: yes/no (all necessary factual claims supported); evidence_sufficient: yes/no/uncertain based on the ENTIRE available corpus, not just retrieved passages; abstention_correct: yes/no/not_applicable. failure_category: retrieval_miss/unsupported_synthesis/missed_contradiction/incorrect_verification/tool_failure/budget_exhaustion/other/none. Two raters independently assess and resolve disagreements.",
        "warning":"Do not expose gold answers or verifier labels before independent citation judging. These blank forms are not completed human evaluation."})
    return {"items":len(rows),"output":str(output)}


def read_labels(path: Path):
    with path.open(encoding="utf-8-sig",newline="") as stream:
        rows=list(csv.DictReader(stream))
    labels={row["item_id"]:row for row in rows if row.get("label")}
    if len(labels)!=sum(bool(row.get("label")) for row in rows):
        raise ValueError("Duplicate item IDs")
    if any(row["label"] not in LABELS for row in labels.values()):
        raise ValueError("Unknown human label")
    return labels


def score_annotations(a_path: Path,b_path: Path,resolved_path: Path,key_path: Path):
    a,b=read_labels(a_path),read_labels(b_path)
    ids=sorted(set(a)&set(b))
    result={"inter_rater":cohen_kappa([a[i]["label"] for i in ids],[b[i]["label"] for i in ids]),
            "only_A":len(set(a)-set(b)),"only_B":len(set(b)-set(a))}
    resolved=read_labels(resolved_path)
    mapping={row["item_id"]:row for row in json.loads(key_path.read_text(encoding="utf-8"))}
    if set(resolved)-set(mapping):
        raise ValueError("Unknown resolved IDs")
    if set(resolved)-set(ids):
        raise ValueError("A resolved item must first have two independent judgments")
    labels=[{**mapping[i],"resolution":row["label"]} for i,row in resolved.items()]
    groups={}
    for mode,scenario in sorted({(x["mode"],x["scenario"]) for x in labels}):
        groups[f"{mode}:{scenario}"]=human_grounding_scores([x for x in labels if (x["mode"],x["scenario"])==(mode,scenario)])
    result.update({"grounding_by_mode_scenario":groups,"resolved_count":len(resolved),"total_items":len(mapping),
                   "coverage_of_annotation":len(resolved)/len(mapping) if mapping else None,
                   "complete":len(resolved)==len(mapping) and len(mapping)>0})
    result["paired_citation_precision"]=[]
    task_key=key_path.parent/"PRIVATE-task-key.json"
    if result["complete"] and task_key.exists():
        # Include zero-claim/zero-citation outputs from the task key in the frame.
        contexts=json.loads(task_key.read_text(encoding="utf-8"))
        for scenario in sorted({x["scenario"] for x in contexts}):
            counts={mode:{x["task_id"]:[0,0] for x in contexts if x["mode"]==mode and x["scenario"]==scenario} for mode in ["multi_step","verified"]}
            for item in labels:
                mode=item["mode"]
                if mode in counts and item["scenario"]==scenario and item.get("evidence_id") and item["resolution"] in {"supported","unsupported","contradicted"}:
                    pair=counts[mode].setdefault(item["task_id"],[0,0])
                    pair[0]+=int(item["resolution"]=="supported");pair[1]+=1
            if all(counts.values()):
                result["paired_citation_precision"].append({"scenario":scenario,"contrast":"verified minus multi_step",**paired_ratio_bootstrap(counts["multi_step"],counts["verified"])})
    else:
        result["paired_citation_precision_status"]="requires complete annotations and PRIVATE-task-key.json"
    return result


def score_tasks(a_path:Path,b_path:Path,resolved_path:Path,key_path:Path):
    def read(path):
        with path.open(encoding="utf-8-sig",newline="") as stream:
            rows=list(csv.DictReader(stream))
        if len({row["item_id"] for row in rows})!=len(rows):
            raise ValueError("Duplicate task annotation IDs")
        return {row["item_id"]:row for row in rows if row.get("answer_correct") in {"yes","no"}}
    a,b,resolved=read(a_path),read(b_path),read(resolved_path)
    key={row["item_id"]:row for row in json.loads(key_path.read_text(encoding="utf-8"))}
    ids=sorted(set(a)&set(b))
    if set(resolved)-set(ids) or set(resolved)-set(key):
        raise ValueError("Resolved task requires matching key and two independent judgments")
    for row in resolved.values():
        for field,allowed in [("required_claims_supported",{"yes","no"}),("evidence_sufficient",{"yes","no","uncertain"}),("abstention_correct",{"yes","no","not_applicable"})]:
            if row.get(field) not in allowed:
                raise ValueError(f"Resolved task must have a valid {field}")
    agreement={}
    for field in ["answer_correct","required_claims_supported","evidence_sufficient","abstention_correct"]:
        comparable=[i for i in ids if a[i].get(field) and b[i].get(field)]
        agreement[field]=cohen_kappa([a[i][field] for i in comparable],[b[i][field] for i in comparable])
    groups={}
    for mode,scenario in sorted({(key[i]["mode"],key[i]["scenario"]) for i in resolved}):
        selected=[(key[i],row) for i,row in resolved.items() if (key[i]["mode"],key[i]["scenario"])==(mode,scenario)]
        successes=[row["answer_correct"]=="yes" and row.get("required_claims_supported")=="yes" and not meta["failed"] for meta,row in selected]
        insufficient=[(meta,row) for meta,row in selected if row.get("evidence_sufficient")=="no"]
        answerable=[(meta,row) for meta,row in selected if row.get("evidence_sufficient")=="yes"]
        groups[f"{mode}:{scenario}"]={"resolved_runs":len(selected),"task_success":sum(successes)/len(successes),
            "manual_answer_accuracy":sum(row["answer_correct"]=="yes" and not meta["failed"] for meta,row in selected)/len(selected),
            "answer_rate_on_answerable":sum(meta["answered"] and not meta["failed"] for meta,row in answerable)/len(answerable) if answerable else None,
            "correct_abstention_rate":sum(not meta["answered"] and not meta["failed"] and row.get("abstention_correct")=="yes" for meta,row in insufficient)/len(insufficient) if insufficient else None,
            "recovery_rate":sum(successes)/len(successes) if scenario in {"timeout","empty","irrelevant"} else None,
            "failure_categories":dict(__import__('collections').Counter(row.get("failure_category") or "unlabeled" for meta,row in selected if meta["failed"] or row["answer_correct"]!="yes" or row.get("required_claims_supported")!="yes"))}
    return {"inter_rater":agreement,"groups":groups,"resolved_count":len(resolved),"total_tasks":len(key),
            "complete":len(resolved)==len(key) and bool(key),"source":"independent human task adjudication with explicit reconciliation"}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest="command",required=True)
    exp=commands.add_parser("export");exp.add_argument("--runs",type=Path,required=True);exp.add_argument("--output",type=Path,required=True)
    score=commands.add_parser("score")
    for arg in ["rater-a","rater-b","resolved","key","output"]:
        score.add_argument("--"+arg,type=Path,required=True)
    taskscore=commands.add_parser("score-tasks")
    for arg in ["rater-a","rater-b","resolved","key","output"]:
        taskscore.add_argument("--"+arg,type=Path,required=True)
    args=parser.parse_args()
    if args.command=="export":
        result=export_annotations(args.runs,args.output)
    elif args.command=="score":
        result=score_annotations(args.rater_a,args.rater_b,args.resolved,args.key)
        write_json(args.output,result)
    else:
        result=score_tasks(args.rater_a,args.rater_b,args.resolved,args.key)
        write_json(args.output,result)
    print(json.dumps(result,ensure_ascii=True))


if __name__=="__main__":
    main()
