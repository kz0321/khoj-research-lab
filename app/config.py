from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env", override=False)
RUNTIME = ROOT / "runtime"
RUNTIME.mkdir(exist_ok=True)
MODELS = ROOT / "models"
MODEL = os.getenv("LLM_MODEL", "deepseek-flash")
BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/")
API_KEY = os.getenv("LLM_API_KEY", "")
STRUCTURED_OUTPUT = os.getenv("LLM_STRUCTURED_OUTPUT", "json_object")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")


@dataclass(frozen=True)
class RetrievalSettings:
    mode: str = "baseline"
    candidates: int = 24
    diversity_margin: float = 0.04

    def __post_init__(self):
        if self.mode not in {"baseline", "enhanced"}:
            raise ValueError("RETRIEVAL_MODE must be baseline or enhanced")
        if not 6 <= self.candidates <= 100:
            raise ValueError("RETRIEVAL_CANDIDATES must be between 6 and 100")
        if not 0 <= self.diversity_margin <= 0.1:
            raise ValueError("RETRIEVAL_DIVERSITY_MARGIN must be between 0 and 0.1")

    def describe(self):
        if self.mode == "baseline":
            return {"mode": "baseline", "tokenizer": "legacy", "reranker": "none"}
        return {"mode": self.mode, "tokenizer": "han-unigram-bigram-v1",
                "reranker": "lexical-coverage-order-v1", "candidates": self.candidates,
                "diversity_margin": self.diversity_margin}


RETRIEVAL = RetrievalSettings(
    mode=os.getenv("RETRIEVAL_MODE", "baseline"),
    candidates=int(os.getenv("RETRIEVAL_CANDIDATES", "24")),
    diversity_margin=float(os.getenv("RETRIEVAL_DIVERSITY_MARGIN", "0.04")),
)
HOST = "127.0.0.1"
PORT = int(os.getenv("PORT", "8778"))
LIMITS = {"decision_rounds": 6, "tool_calls": 12, "repair_rounds": 2,
          "elapsed_seconds": int(os.getenv("RUN_TIMEOUT_SECONDS", "240")),
          "model_calls": 16, "retrieval_top_k": 6, "max_claims": 8,
          "max_evidence": 30, "final_answer_tokens": 1800}
# Prices are deliberately unset unless a user supplies a documented tariff.
INPUT_PRICE = os.getenv("INPUT_USD_PER_MILLION", "")
OUTPUT_PRICE = os.getenv("OUTPUT_USD_PER_MILLION", "")
PRICING_DATE = os.getenv("PRICING_DATE", "")
