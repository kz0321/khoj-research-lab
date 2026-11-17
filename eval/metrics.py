"""Answer, evidence, efficiency and human-label metrics.

Checker statuses are NEVER converted into human citation-support ground truth.
"""
from __future__ import annotations

import math
import random
import re
import statistics
import string
from collections import Counter


def normalize_answer(value: str) -> str:
    value = value.lower()
    value = "".join(ch for ch in value if ch not in string.punctuation)
    value = re.sub(r"\b(a|an|the)\b", " ", value)
    return " ".join(value.split())


def answer_scores(prediction: str, reference: str) -> dict:
    prediction, reference = normalize_answer(prediction), normalize_answer(reference)
    em = float(prediction == reference)
    # Match the official HotpotQA yes/no/noanswer special case.
    special = {"yes", "no", "noanswer"}
    if (prediction in special or reference in special) and prediction != reference:
        return {"em": em, "f1": 0.0, "precision": 0.0, "recall": 0.0}
    predicted, gold = prediction.split(), reference.split()
    common = sum((Counter(predicted) & Counter(gold)).values())
    if not common:
        return {"em": em, "f1": 0.0, "precision": 0.0, "recall": 0.0}
    precision, recall = common / len(predicted), common / len(gold)
    return {"em": em, "f1": 2 * precision * recall / (precision + recall), "precision": precision, "recall": recall}


def supporting_fact_scores(prediction: list, reference: list) -> dict:
    predicted, gold = set(map(tuple, prediction)), set(map(tuple, reference))
    common = len(predicted & gold)
    precision = common / len(predicted) if predicted else 0.0
    recall = common / len(gold) if gold else 0.0
    return {"em": float(predicted == gold), "f1": 2*precision*recall/(precision+recall) if precision+recall else 0.0,
            "precision": precision, "recall": recall}


def percentile(values, probability: float):
    if not values:
        return None
    values = sorted(values)
    x = (len(values) - 1) * probability
    lo, hi = math.floor(x), math.ceil(x)
    return values[lo] + (values[hi] - values[lo]) * (x - lo)


def paired_bootstrap(left: dict[str, float], right: dict[str, float], *, seed=20261116, samples=2000) -> dict:
    """Return right-minus-left; resample TASKS, never individual claims or repeats."""
    ids = sorted(set(left) & set(right))
    if not ids:
        return {"n_tasks": 0, "difference": None, "ci95": None}
    differences = [right[i] - left[i] for i in ids]
    rng = random.Random(seed)
    means = [statistics.fmean(rng.choices(differences, k=len(differences))) for _ in range(samples)]
    return {"n_tasks": len(ids), "difference": statistics.fmean(differences),
            "ci95": [percentile(means, .025), percentile(means, .975)], "bootstrap_samples": samples,
            "seed": seed, "interpretation": "descriptive task-level interval; tiny development pilots do not establish held-out improvement"}


def cohen_kappa(first: list[str], second: list[str]) -> dict:
    if len(first) != len(second):
        raise ValueError("Raters must label the same item IDs")
    if not first:
        return {"n": 0, "agreement": None, "kappa": None}
    n = len(first)
    observed = sum(a == b for a,b in zip(first,second)) / n
    p, q = Counter(first), Counter(second)
    expected = sum(p[label]*q[label] for label in p.keys() | q.keys()) / (n*n)
    return {"n": n, "agreement": observed, "kappa": (observed-expected)/(1-expected) if expected < 1 else None,
            "undefined_reason": "all labels have one category" if expected == 1 else None}


def paired_ratio_bootstrap(left: dict[str, tuple[float,float]], right: dict[str, tuple[float,float]], *, seed=20261116, samples=2000) -> dict:
    """Paired task resampling of a ratio of totals, e.g. micro citation precision.

    Zero-citation tasks have (0, 0), are retained in the task sampling frame and
    never receive invented perfect precision. Undefined bootstrap samples are disclosed.
    """
    ids=sorted(set(left)&set(right))
    def ratio(values):
        numerator=sum(v[0] for v in values);denominator=sum(v[1] for v in values)
        return numerator/denominator if denominator else None
    l=ratio([left[i] for i in ids]);r=ratio([right[i] for i in ids])
    if l is None or r is None:
        return {"n_tasks":len(ids),"difference":None,"ci95":None,"undefined_reason":"one condition has no annotated denominator"}
    rng=random.Random(seed);differences=[]
    for _ in range(samples):
        drawn=rng.choices(ids,k=len(ids));a=ratio([left[i] for i in drawn]);b=ratio([right[i] for i in drawn])
        if a is not None and b is not None:differences.append(b-a)
    return {"n_tasks":len(ids),"difference":r-l,"ci95":[percentile(differences,.025),percentile(differences,.975)] if differences else None,
            "bootstrap_samples":samples,"undefined_bootstrap_samples":samples-len(differences),"seed":seed,
            "estimand":"difference of micro ratios, paired resampling at task level"}


def human_grounding_scores(labels: list[dict]) -> dict:
    """Only resolved external annotations qualify; checker outputs are not accepted.

    One label per externally verifiable claim-citation pair, or an uncited claim
    with evidence_id="". A claim is covered if at least one cited pair is supported.
    """
    valid = [r for r in labels if r.get("resolution") in {"supported", "unsupported", "contradicted"}]
    pairs = [r for r in valid if r.get("evidence_id")]
    claims = {}
    for r in valid:
        key = (r["task_id"], r["run_id"], r["claim_id"])
        claims.setdefault(key, False)
        claims[key] |= bool(r.get("evidence_id")) and r["resolution"] == "supported"
    return {"annotated_pairs": len(pairs), "annotated_claims": len(claims),
            "citation_support_precision": sum(r["resolution"] == "supported" for r in pairs)/len(pairs) if pairs else None,
            "citation_coverage": sum(claims.values())/len(claims) if claims else None,
            "unsupported_claim_rate": 1-sum(claims.values())/len(claims) if claims else None,
            "source": "resolved human annotations only"}


def visible_claims(result: dict) -> list[dict]:
    """Mirror deterministic report rendering; discarded ledger drafts are not output claims."""
    gate = result.get("mode") in {"verified", "verified_no_repair"}
    return [claim for claim in result.get("claims", [])
            if (not gate or claim.get("status") == "supported")
            and (claim.get("id") != "A0" or bool(result.get("answer")))]


def task_score(task: dict, response: dict) -> dict:
    result = response.get("result") or {}
    answer = str(result.get("answer") or "")
    score = answer_scores(answer, str(task["answer"]))
    failed = response.get("status") != "completed"
    if failed:
        score = {key: 0.0 for key in score}
    score = {"answer_"+key: value for key,value in score.items()}
    predicted_sp = result.get("supporting_facts", [])
    if not predicted_sp:
        # Only cited evidence is eligible; retrieval alone does not count as prediction.
        cited = {source for claim in visible_claims(result) for source in claim.get("evidence_ids", [])}
        for evidence in result.get("evidence", []):
            if evidence.get("id") not in cited:
                continue
            metadata = evidence.get("metadata") or {}
            ids = evidence.get("sentence_ids", metadata.get("sentence_ids", []))
            if not ids:
                location = evidence.get("location", "")
                if isinstance(location, dict):
                    ids = location.get("sentence_ids", [])
                elif isinstance(location, str):
                    match = re.search(r"sentence[s]?\s*[:=]?\s*(\d+)(?:\s*[-:]\s*(\d+))?", location, re.I)
                    if match:
                        a, b = int(match[1]), int(match[2] or match[1])
                        ids = list(range(a,b+1))
            predicted_sp.extend([[evidence["title"], int(i)] for i in ids])
    if "supporting_facts" in task:
        sp = supporting_fact_scores(predicted_sp if not failed else [], task["supporting_facts"])
        score.update({"supporting_"+key: value for key,value in sp.items()})
    score.update({"failed": failed, "answered": bool(answer.strip()) and not failed,
                  "elapsed_seconds": result.get("elapsed_seconds", response.get("client_elapsed_seconds")),
                  "usage": result.get("usage", {}), "tool_calls":result.get("tool_calls",0),
                  "model_calls":len(result.get("model_calls",[])), "predicted_supporting_facts": predicted_sp})
    return score
