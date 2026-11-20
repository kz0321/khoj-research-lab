"""Diagnostic probe for checker semantic edge cases and repair-loop behavior.

Runs against an isolated temporary SQLite store without touching runtime/.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config
from app.agent import ResearchAgent
from app.retrieval import Retriever
from app.schemas import Claim, Draft, ResearchRequest
from app.store import Store


def make_row(key, text, title="Synthetic Doc"):
    return {
        "id": key,
        "source_id": f"src-{key}",
        "title": title,
        "text": text,
        "location": {"start_line": 1, "end_line": 5},
        "url": None,
    }


def run_checker_probes(retriever):
    results = {}

    # Probe 1: Entity role-swap false positive trap (fictional names to avoid pretraining memory)
    agent1 = ResearchAgent(
        ResearchRequest(question="Did Julian Mercer win the 2022 Valois Medal?", mode="verified"),
        retriever,
    )
    agent1.add_evidence([
        make_row(
            "p1",
            "Julian Mercer is an acoustic engineer who co-produced the 2021 track 'Horizon' "
            "with the violinist Devon Hale, who grew up in Lyon, France and won the 2022 Valois Medal.",
            "Production Credits.md",
        )
    ])
    draft1 = Draft(
        claims=[
            Claim(
                id="C1",
                text="Julian Mercer grew up in Lyon, France and won the 2022 Valois Medal.",
                evidence_ids=["E1"],
            )
        ]
    )
    verdicts1, _ = agent1.verify(draft1)
    results["probe1_role_swap_trap"] = {
        "expected_not": "supported",
        "actual_status": verdicts1[0]["status"],
        "reason": verdicts1[0]["reason"],
        "passed": verdicts1[0]["status"] != "supported",
    }

    # Probe 2: Joint multi-passage bridge entailment
    agent2 = ResearchAgent(
        ResearchRequest(question="Where was Project Kestrel's sensor array deployed?", mode="verified"),
        retriever,
    )
    agent2.add_evidence([
        make_row("p2a", "Project Kestrel is the internal codename used by Dr. Linnea Lindqvist throughout 2023.", "Codename Log.md"),
        make_row("p2b", "In November 2023, Dr. Linnea Lindqvist deployed the sensor array in Bergen, Norway.", "Field Report.md"),
    ])
    draft2 = Draft(
        answer="Bergen, Norway",
        answer_statement="Project Kestrel's sensor array was deployed in Bergen, Norway in November 2023.",
        answer_evidence_ids=["E1", "E2"],
        claims=[
            Claim(
                id="C1",
                text="Dr. Linnea Lindqvist used the codename Project Kestrel and deployed the sensor array in Bergen, Norway in November 2023.",
                evidence_ids=["E1", "E2"],
            )
        ],
    )
    verdicts2, _ = agent2.verify(draft2)
    results["probe2_joint_bridge"] = {
        "expected": "supported",
        "A0_status": verdicts2[0]["status"],
        "A0_reason": verdicts2[0]["reason"],
        "C1_status": verdicts2[1]["status"],
        "passed": verdicts2[0]["status"] == "supported" and verdicts2[1]["status"] == "supported",
    }

    # Probe 3: A0 formatting mismatch (comma/whitespace in numbers)
    agent3 = ResearchAgent(
        ResearchRequest(question="What throughput did the prototype achieve?", mode="verified"),
        retriever,
    )
    agent3.add_evidence([
        make_row("p3", "The prototype achieved a throughput of 1,500 requests per second on 2024-03-15.", "Benchmarks.md")
    ])
    draft3 = Draft(
        answer="1,500 requests per second",
        answer_statement="The prototype achieved a throughput of 1500 requests per second.",
        answer_evidence_ids=["E1"],
        claims=[],
    )
    verdicts3, _ = agent3.verify(draft3)
    results["probe3_a0_numeric_format"] = {
        "expected": "supported",
        "A0_status": verdicts3[0]["status"],
        "A0_reason": verdicts3[0]["reason"],
        "validation_issue": verdicts3[0].get("validation_issue"),
        "passed": verdicts3[0]["status"] == "supported",
    }
    return results


def run_e2e_repair_probe(store, retriever):
    cid = store.create_collection("Probe Multi-hop", "probe-mh")
    filler = " ".join(["Calibration baseline step checked with standard voltage and ambient airflow."] * 20)
    docs = [
        {
            "id": "d1",
            "title": "01-overview.md",
            "text": (
                "# Project Helios Overview\n\n"
                "Project Helios is a battery thermal test conducted by Lab Beta. "
                "The lead researcher's alias in the log is Alpha-7. "
                "See the personnel directory and detailed test appendix for full names and scores."
            ),
        },
        {
            "id": "d2",
            "title": "02-directory.md",
            "text": (
                "# Lab Beta Personnel\n\n"
                "- Alpha-7: Dr. Soren Lindholm (Lead Thermal Engineer)\n"
                "- Alpha-9: Dr. Maya Chen (Optics Lead)"
            ),
        },
        {
            "id": "d3",
            "title": "03-appendix.md",
            "text": (
                "# Detailed Test Appendix\n\n"
                f"## Section 1: Setup\n{filler}\n\n"
                "## Section 2: Final Measurement\n"
                "For Dr. Soren Lindholm's test series, the peak thermal stability score recorded was 94.2% under 400W load."
            ),
        },
    ]
    for doc in docs:
        retriever.ingest(cid, doc)

    question = "Who is Alpha-7 in Project Helios, and what peak thermal stability score (in %) did their test series achieve?"
    agent = ResearchAgent(
        ResearchRequest(question=question, collection_id=cid, mode="verified", allow_web=False),
        retriever,
        progress=lambda x: print(f"  [e2e] {x['stage']}: {x['message']}", flush=True),
    )
    out = agent.run()
    has_name = "soren lindholm" in out["answer"].lower()
    has_score = "94.2%" in out["answer"] or "94.2" in out["answer"]
    return {
        "question": question,
        "answer": out["answer"],
        "stop_reason": out["stop_reason"],
        "rounds": out["rounds"],
        "tool_calls": out["tool_calls"],
        "repair_rounds": out["repair_rounds"],
        "format_repair_rounds": out["format_repair_rounds"],
        "trace_tools": [{"round": t.get("round"), "tool": t["tool"], "args": t["args"], "status": t["status"]} for t in out["trace"]],
        "passed": has_name and has_score,
    }


def main():
    if not config.model_configured():
        raise SystemExit("LLM_API_KEY not configured in .env")
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs/validation/probe-before-20261120.json"
    with tempfile.TemporaryDirectory(prefix="khoj-probe-") as tmpdir:
        store = Store(Path(tmpdir) / "probe.sqlite3")
        retriever = Retriever(store)
        print("Running checker semantic probes...", flush=True)
        checker_results = run_checker_probes(retriever)
        print("Running E2E multi-hop repair probe...", flush=True)
        e2e_result = run_e2e_repair_probe(store, retriever)

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "agent_policy": config.AGENT_POLICY,
        "model": config.MODEL,
        "checker_probes": checker_results,
        "e2e_repair_probe": e2e_result,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nSaved probe report to {output_path}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()