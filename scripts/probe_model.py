"""Make one small, potentially billable structured model call using local .env.

Unlike GET /models, this checks generation and the application's JSON parser.
Never prints the credential, request headers or environment contents.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
from typing import Literal

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config
from app.llm import ModelClient, redact


class ProbeResult(BaseModel):
    status: Literal["ok"]


def probe():
    started = time.monotonic()
    client = ModelClient(started + 65)
    outcome = {"checked_at": datetime.now(timezone.utc).isoformat(),
               "base_url": config.BASE_URL, "requested_model": config.MODEL,
               "structured_output": config.STRUCTURED_OUTPUT, "passed": False}
    original_cap = config.LIMITS["model_calls"]
    config.LIMITS["model_calls"] = 1
    try:
        response = client.structured("connection_probe", "Return the requested JSON object.",
            {"instruction": "Return exactly {\"status\":\"ok\"}."}, ProbeResult, max_tokens=128)
        outcome.update(passed=True, result=response.model_dump())
    except Exception as error:
        outcome["error"] = redact(error)
    finally:
        config.LIMITS["model_calls"] = original_cap
    outcome.update(elapsed_seconds=round(time.monotonic() - started, 3),
                   usage=client.usage_summary(), model_calls=client.events)
    return outcome


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = probe()
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    raise SystemExit(0 if result["passed"] else 1)
