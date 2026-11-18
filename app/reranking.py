"""Bounded, deterministic passage scoring for the enhanced retrieval mode."""
from __future__ import annotations

import re


# Split Han runs before matching Unicode words. Python's \w includes Han.
HAN_RUN = re.compile(r"([\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002fa1f\U00030000-\U000323af]+)")
WORD = re.compile(r"\w+")


def mixed_tokens(text, *, bigrams=True):
    tokens = []
    for index, part in enumerate(HAN_RUN.split(text.casefold())):
        if index % 2:
            tokens.extend(part)
            if bigrams:
                tokens.extend(part[i:i + 2] for i in range(len(part) - 1))
        else:
            tokens.extend(WORD.findall(part))
    return tokens


def rerank(query, candidates, idf):
    """Score question coverage and local word order. Keep RRF as a ranking prior."""
    query_words = mixed_tokens(query[:512], bigrams=False)
    weights = {word: max(0.1, idf.get(word, 1.0)) for word in query_words}
    total_weight = sum(weights.values()) or 1.0
    query_pairs = set(zip(query_words, query_words[1:]))

    def coverage(words):
        return sum(weights[word] for word in weights if word in words) / total_weight

    ranked = []
    for rank, row in enumerate(candidates):
        words = mixed_tokens(row["text"][:1000], bigrams=False)
        word_set = set(words)
        title_words = set(mixed_tokens(row["title"][:150], bigrams=False))
        body_match = coverage(word_set)
        if query_pairs:
            ordered_match = len(query_pairs.intersection(zip(words, words[1:]))) / len(query_pairs)
        else:
            ordered_match = body_match
        lexical = 0.65 * body_match + 0.25 * ordered_match + 0.10 * coverage(title_words)
        combined = 0.70 * lexical + 0.30 / (1 + rank / 10)
        ranked.append(dict(row, lexical_score=lexical, rerank_score=combined))
    return sorted(ranked, key=lambda row: -row["rerank_score"])


def select_evidence(ranked, top_k, margin):
    """Keep the best occurrence of each passage, then diversify close matches."""
    remaining = []
    seen_text = set()
    seen_ids = set()
    for row in ranked:
        fingerprint = " ".join(row["text"].split())
        if row["id"] not in seen_ids and fingerprint not in seen_text:
            remaining.append(row)
            seen_ids.add(row["id"])
            seen_text.add(fingerprint)

    selected = []
    sources = set()
    while remaining and len(selected) < top_k:
        best = remaining[0]
        index = 0
        if margin > 0 and best["source_id"] in sources:
            for position, row in enumerate(remaining[1:], start=1):
                if best["rerank_score"] - row["rerank_score"] > margin:
                    break
                if row["source_id"] not in sources and row["lexical_score"] > 0:
                    index = position
                    break
        row = remaining.pop(index)
        sources.add(row["source_id"])
        selected.append(row)
    return selected
