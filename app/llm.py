from __future__ import annotations

import json
import re
import time
from urllib.parse import urlparse
import httpx
from . import config

class ModelError(RuntimeError):
    pass

def redact(message):
    value = str(message)
    if config.API_KEY:
        value = value.replace(config.API_KEY, "[REDACTED]")
    return re.sub(r"\bsk-[A-Za-z0-9_-]{12,}", "[REDACTED]", value)[:500]


def completion_content(data):
    """Validate the provider envelope before passing text to the JSON schema."""
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ModelError("Model response must contain a nonempty choices list")
    choice = choices[0]
    message = choice.get("message")
    # Some compatible gateways flatten the complete assistant message into
    # the choice itself. Do not mistake an incremental delta for a message.
    if "message" not in choice and choice.get("role") == "assistant" and "delta" not in choice:
        message = choice
    if not isinstance(message, dict):
        if "delta" in choice:
            raise ModelError("Model returned a streaming delta; a complete non-streaming message is required")
        raise ModelError("Model response is missing choices[0].message")
    if message.get("refusal"):
        raise ModelError("Model refused the request: " + redact(message["refusal"]))
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ModelError("Model response message.content must be nonempty text")
    # A gateway may add plain-language commentary. Accept only one complete
    # JSON fence on its own lines, with no other code fence or JSON object /
    # array in the surrounding commentary. Schema validation still owns
    # the contents; never guess JSON boundaries or repair incomplete JSON.
    fenced = re.fullmatch(r"(?:[^`{}\[\]]*\r?\n)?```(?:json)?[ \t]*\r?\n(.*?)\r?\n```(?:\r?\n[^`{}\[\]]*)?",
                         content.strip(), re.DOTALL | re.IGNORECASE)
    if fenced:
        content = fenced.group(1)
    return content, choice.get("finish_reason")

class ModelClient:
    def __init__(self, deadline, cancelled=lambda: False):
        self.deadline, self.cancelled = deadline, cancelled
        self.usage = {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                      "failed_attempts": 0, "unknown_usage_attempts": 0}
        self.events = []

    def structured(self, stage, system, payload, schema, max_tokens=1800):
        if not config.model_configured():
            raise ModelError("LLM_API_KEY is not configured in .env")
        format_instruction = "\nReturn only a JSON object matching this schema: " + json.dumps(schema.model_json_schema())
        request = {"model": config.MODEL, "messages": [
            {"role": "system", "content": system + format_instruction},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
            "temperature": 0, "max_tokens": max_tokens, "stream": False,
            "response_format": {"type": "json_object"}}
        if config.STRUCTURED_OUTPUT == "json_schema":
            request["response_format"] = {"type": "json_schema", "json_schema": {
                "name": schema.__name__, "schema": schema.model_json_schema(), "strict": True}}
        if urlparse(config.BASE_URL).hostname == "api.deepseek.com":
            # DeepSeek Flash defaults can spend max_tokens on thinking with empty final content.
            # All experimental modes explicitly share the same non-thinking generation setting.
            request["thinking"] = {"type": "disabled"}
        for attempt in range(2):
            if self.cancelled():
                raise ModelError("Cancelled by user")
            remaining = self.deadline - time.monotonic()
            if remaining <= 1 or self.usage["calls"] >= config.LIMITS["model_calls"]:
                raise ModelError("Model/time budget exhausted")
            begin = time.monotonic()
            self.usage["calls"] += 1
            event = {"stage": stage, "attempt": attempt + 1, "model": config.MODEL, "status": "failed"}
            data = None
            usage_known = False
            try:
                with httpx.Client(timeout=min(70, remaining), trust_env=True) as client:
                    response = client.post(config.BASE_URL + "/chat/completions", json=request,
                        headers={"Authorization": "Bearer " + config.API_KEY})
                try:
                    data = response.json()
                except ValueError:
                    data = None
                usage = data.get("usage") if isinstance(data, dict) else None
                if isinstance(usage, dict) and all(isinstance(usage.get(k), int) and usage[k] >= 0 for k in ("prompt_tokens", "completion_tokens")):
                    self.usage["input_tokens"] += usage["prompt_tokens"]
                    self.usage["output_tokens"] += usage["completion_tokens"]
                    usage_known = True
                    event.update(input_tokens=usage["prompt_tokens"], output_tokens=usage["completion_tokens"])
                if response.status_code >= 400:
                    raise ModelError(f"Model HTTP {response.status_code}: " + redact(response.text))
                if not isinstance(data, dict):
                    raise ModelError("Model returned an invalid response object")
                event["returned_model"] = data.get("model")
                content, finish_reason = completion_content(data)
                event["finish_reason"] = finish_reason
                if finish_reason == "length":
                    raise ModelError("Model output reached max_tokens before completing the structured result")
                parsed = schema.model_validate_json(content)
                if self.cancelled():
                    raise ModelError("Cancelled by user")
                if time.monotonic() >= self.deadline:
                    raise ModelError("Elapsed-time budget exhausted during model request")
                event["status"] = "completed"
                return parsed
            except Exception as error:
                self.usage["failed_attempts"] += 1
                event["error"] = redact(error)
                # Retry transient transport/service failures once. Invalid JSON/schema is explicit failure.
                transient = isinstance(error, (httpx.TimeoutException, httpx.NetworkError)) or any(
                    x in str(error) for x in ("HTTP 429", "HTTP 500", "HTTP 502", "HTTP 503", "HTTP 504"))
                if attempt or not transient:
                    raise ModelError(f"{stage}: {redact(error)}") from None
            finally:
                if not usage_known:
                    self.usage["unknown_usage_attempts"] += 1
                event["elapsed_seconds"] = round(time.monotonic() - begin, 3)
                self.events.append(event)
        raise ModelError("Model request failed")

    def usage_summary(self):
        result = dict(self.usage)
        result.update(estimated_cost_usd=None, pricing_date=config.PRICING_DATE or None)
        if config.INPUT_PRICE and config.OUTPUT_PRICE and config.PRICING_DATE:
            result["estimated_cost_usd"] = (result["input_tokens"] * float(config.INPUT_PRICE)
                + result["output_tokens"] * float(config.OUTPUT_PRICE)) / 1_000_000
        result["cost_note"] = "Token counts include all received usage; failed requests without usage remain unknown. No tariff configured." if result["estimated_cost_usd"] is None else "Estimate from configured tariff; unknown-usage requests excluded."
        return result
