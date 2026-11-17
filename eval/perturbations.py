"""Deterministic controlled perturbations, applied without exposing gold to the agent."""
from __future__ import annotations
import copy
import hashlib


def withhold_support(documents: list[dict], supporting_facts: list[list]) -> list[dict]:
    excluded = {(str(title), int(index)) for title,index in supporting_facts}
    result = []
    for original in documents:
        doc = copy.deepcopy(original)
        # Retain original IDs; never renumber the remaining sentences.
        kept = [s for s in doc.get("sentences", []) if (doc["title"], int(s["id"])) not in excluded]
        doc["sentences"] = kept
        doc["text"] = "\n".join(s["text"] for s in kept)
        doc["sha256"] = hashlib.sha256(doc["text"].encode()).hexdigest()
        if doc["text"].strip():
            result.append(doc)
    return result


def tool_perturbation(kind: str, seed: int = 20261116) -> dict | None:
    if kind in {"clean", "withhold_support"}:
        return None
    if kind not in {"timeout", "empty", "irrelevant"}:
        raise ValueError("Unknown perturbation")
    return {"kind": kind, "tool_attempt": 1, "seed": seed}
