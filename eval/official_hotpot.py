"""Run the pinned official HotpotQA evaluator on a recorded mode/repeat.

python -m eval.official_hotpot --runs eval/results/development-pilot/runs.jsonl --mode verified --split dev --output eval/results/development-pilot/official-verified
"""
from __future__ import annotations
import argparse
import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from eval.prepare_data import ROOT, DATA, write_json
from eval.run import read_jsonl


def evaluate(runs:Path, mode:str, split:str, repeat:int, scenario:str, output:Path):
    tasks={t["id"]:t for t in read_jsonl(DATA/"evaluation"/f"hotpotqa-{split}.jsonl")}
    rows=[r for r in read_jsonl(runs) if r["dataset"]=="hotpotqa" and r["mode"]==mode and r["repeat"]==repeat and r["scenario"]==scenario and r["split"]==split]
    # Last attempt per ID wins only when a runner explicitly retried a failed run.
    rows=list({row["task_id"]:row for row in rows}.values())
    if not rows:
        raise ValueError("No recorded runs match the requested configuration")
    gold=[];pred={"answer":{},"sp":{}}
    for row in rows:
        task=tasks[row["task_id"]];identity=task["original_id"]
        gold.append({"_id":identity,"answer":task["answer"],"supporting_facts":task["supporting_facts"]})
        failed=row["scores"]["failed"]
        pred["answer"][identity]="" if failed else (row["response"].get("result") or {}).get("answer","")
        pred["sp"][identity]=[] if failed else row["scores"].get("predicted_supporting_facts",[])
    output.mkdir(parents=True,exist_ok=True)
    write_json(output/"gold.json",gold);write_json(output/"predictions.json",pred)
    completed=subprocess.run([sys.executable,str(ROOT/"eval"/"vendor"/"hotpot_evaluate_v1.py"),str(output/"predictions.json"),str(output/"gold.json")],
                             capture_output=True,text=True,encoding="utf-8",env={**os.environ,"PYTHONUTF8":"1"},check=True)
    metrics=ast.literal_eval(completed.stdout.strip().splitlines()[-1])
    result={"mode":mode,"split":split,"repeat":repeat,"scenario":scenario,"attempted_tasks":len(rows),
            "metrics":metrics,"scorer":"Pinned HotpotQA official evaluator; only ujson import replaced with stdlib json",
            "source":json.loads((ROOT/"eval"/"vendor"/"SOURCE.json").read_text(encoding="utf-8"))}
    write_json(output/"metrics.json",result)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs",type=Path,required=True)
    parser.add_argument("--mode",default="verified")
    parser.add_argument("--split",choices=["dev","test"],default="dev")
    parser.add_argument("--repeat",type=int,default=0)
    parser.add_argument("--scenario",default="clean")
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(evaluate(args.runs,args.mode,args.split,args.repeat,args.scenario,args.output)))


if __name__=="__main__":main()
