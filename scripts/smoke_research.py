"""Run one potentially billable research task and verify JSON/Markdown exports.

Uses the public synthetic demo documents; web search stays disabled. This checks
the complete application flow, not general model accuracy or benchmark gains.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import httpx

QUESTION = "Compare Aurora and Boreal. Are their reported scores directly comparable, and what evidence is still missing?"


def check(api, output, mode, question=QUESTION):
    output.mkdir(parents=True, exist_ok=False)
    with httpx.Client(base_url=api, timeout=60, trust_env=False) as client:
        status = client.get("/api/status")
        status.raise_for_status()
        if not status.json().get("configured"):
            raise RuntimeError("Configure the model before running a live smoke check")
        demo = client.post("/api/demo", timeout=120)
        demo.raise_for_status()
        submitted = client.post("/api/research", json={"question": question, "mode": mode,
            "collection_id": demo.json()["collection_id"], "allow_web": False})
        submitted.raise_for_status()
        run_id = submitted.json()["id"]
        (output / "submitted.json").write_text(json.dumps(submitted.json(), indent=2), encoding="utf-8")
        print(json.dumps({"run_id": run_id, "status": "submitted"}), flush=True)
        started = time.monotonic()
        previous = None
        while time.monotonic() - started < status.json()["limits"]["elapsed_seconds"] + 90:
            response = client.get(f"/api/runs/{run_id}")
            response.raise_for_status()
            run = response.json()
            progress = run.get("progress") or []
            stage = (run["status"], progress[-1].get("stage") if progress else None)
            if stage != previous:
                print(json.dumps({"status": stage[0], "stage": stage[1]}, ensure_ascii=False), flush=True)
                previous = stage
            if run["status"] not in {"queued", "running"}:
                break
            time.sleep(2)
        else:
            client.post(f"/api/runs/{run_id}/cancel")
            raise RuntimeError(f"Polling timed out; cancellation requested for {run_id}; inspect it before retrying")
        (output / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
        result = run.get("result") or {}
        checks = {"completed": run["status"] == "completed", "has_answer": bool(result.get("answer")),
                  "has_evidence": bool(result.get("evidence")), "web_disabled": run.get("request", {}).get("allow_web") is False}
        if result:
            for extension in ("json", "md"):
                exported = client.get(f"/api/runs/{run_id}/export", params={"format": extension})
                exported.raise_for_status()
                (output / f"report.{extension}").write_bytes(exported.content)
                checks[f"{extension}_export_matches"] = (exported.json().get("id") == run_id if extension == "json"
                                                         else exported.text == result.get("report"))
        evidence = {e["id"]: e for e in result.get("evidence", [])}
        supported = [c for c in result.get("claims", []) if c["status"] == "supported"]
        if mode == "verified":
            checks["supported_answer"] = any(c["id"] == "A0" for c in supported)
            checks["exact_cited_quotes"] = bool(supported) and all(c["evidence_ids"]
                and len(c["evidence_ids"]) == len(c["quotes"])
                and all(eid in evidence and quote.strip() and quote in evidence[eid]["text"]
                        for eid, quote in zip(c["evidence_ids"], c["quotes"])) for c in supported)
        summary = {"run_id": run_id, "mode": mode, "question": question, "model": status.json()["model"],
                   "checks": checks, "passed": all(checks.values()), "usage": result.get("usage"),
                   "elapsed_seconds": result.get("elapsed_seconds"), "error": run.get("error"),
                   "supported_claims": len(supported), "total_claims": len(result.get("claims", [])),
                   "scope": "One synthetic demo question; automated checks are not independent semantic evaluation."}
        (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
        return summary["passed"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:8789")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mode", choices=("single_rag", "verified"), default="verified")
    parser.add_argument("--question", default=QUESTION)
    args = parser.parse_args()
    raise SystemExit(0 if check(args.api, args.output, args.mode, args.question) else 1)
