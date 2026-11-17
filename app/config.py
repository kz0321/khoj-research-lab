from __future__ import annotations

import os
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
