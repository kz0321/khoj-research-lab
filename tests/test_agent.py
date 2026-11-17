"""Behavioral tests: no paid/model-network calls and no public benchmark answers.

Scripted model outputs are adversarial inputs for the evidence gate, not quality
measurements. Retrieval/LLM call counts and final observable behavior are checked.
"""
from collections import deque
import threading
import time

import httpx
import pytest

from app import config
from app.agent import ResearchAgent, deterministic_issue
from app.llm import ModelClient, ModelError, redact
from app.schemas import Claim, Decision, Draft, ResearchRequest, ToolAction, Verification


def row(key="a", text="Paris hosted the 2024 event."):
    return {"id": key, "source_id": "source-" + key, "title": "Document " + key,
            "text": text, "location": {"sentence_ids": [0]}, "url": None}


class FakeRetriever:
    def __init__(self, responses=None):
        self.responses = deque(responses or [])
        self.calls = []

    def search(self, collection, query, top_k):
        self.calls.append(("search", collection, query))
        response = self.responses.popleft() if self.responses else [row()]
        if isinstance(response, Exception):
            raise response
        return response

    def read_file(self, collection, path, start=None, end=None):
        self.calls.append(("read", collection, path))
        return [row()]


class ScriptedModel:
    def __init__(self, script):
        self.script = deque(script)
        self.events = []
        self.payloads = []

    def structured(self, stage, system, payload, schema, max_tokens=1800):
        assert self.script, f"Unexpected model call: {stage}"
        expected, response = self.script.popleft()
        assert stage == expected, f"Expected {expected}, got {stage}"
        self.events.append({"stage": stage, "status": "completed"})
        self.payloads.append(payload)
        return schema.model_validate(response)

    def usage_summary(self):
        return {"calls": len(self.events), "input_tokens": 0, "output_tokens": 0}


def make_agent(script=(), mode="verified", retriever=None, **request_args):
    client = ScriptedModel(script)
    agent = ResearchAgent(
        ResearchRequest(question="Which city hosted the 2024 event?", mode=mode, **request_args),
        retriever or FakeRetriever(), client_factory=lambda *_: client,
    )
    return agent, client


SEARCH = {"actions": [{"name": "semantic_search_files", "args": {"q": "host city"}}]}
ANSWER = {"answer": "Paris", "answer_statement": "Paris hosted the 2024 event.",
          "answer_evidence_ids": ["E1"], "claims": []}


def verdict(claim_id="C1", status="supported", ids=None, quotes=None):
    return {"claim_id": claim_id, "status": status, "reason": "Test verdict",
            "evidence_ids": ["E1"] if ids is None else ids,
            "quotes": ["Paris hosted the 2024 event."] if quotes is None else quotes}


@pytest.mark.parametrize("claim,issue", [
    (Claim(id="C1", text="Paris", evidence_ids=[]), "No cited"),
    (Claim(id="C1", text="Paris", evidence_ids=["E99"]), "do not exist"),
    (Claim(id="C1", text="Paris hosted the 2025 event.", evidence_ids=["E1"]), "Numerical"),
])
def test_citation_and_numeric_errors_fail_before_semantic_check(claim, issue):
    assert issue in deterministic_issue(claim, {"E1": row()})


def test_numbers_match_values_with_comma_separator_but_not_percent_units():
    evidence = {"E1": row(text="The sample had 1,200 observations; success was 20%.")}
    assert deterministic_issue(Claim(id="C", text="There were 1200 observations.", evidence_ids=["E1"]), evidence) is None
    assert deterministic_issue(Claim(id="C", text="Success was 20.", evidence_ids=["E1"]), evidence)


def test_research_summary_can_cite_multiple_claims_sources_within_evidence_budget():
    ids = [f"E{i}" for i in range(1, 13)]
    assert Draft(answer="A review of several sources.", answer_evidence_ids=ids).answer_evidence_ids == ids
    with pytest.raises(ValueError):
        Draft(answer_evidence_ids=[f"E{i}" for i in range(1, 32)])


@pytest.mark.parametrize("selected_ids", [["E1"], [f"E{i}" for i in range(1, 13)]])
def test_multi_source_summary_reaches_and_passes_semantic_checker(selected_ids):
    agent, model = make_agent([("verify", {"verdicts": [verdict(
        claim_id="A0", ids=selected_ids,
        quotes=["Paris hosted the 2024 event."] * len(selected_ids))]})])
    agent.add_evidence([row(str(i)) for i in range(12)])
    claims, _ = agent.verify(Draft(**{**ANSWER, "answer_evidence_ids": [f"E{i}" for i in range(1, 13)]}))
    assert claims[0]["status"] == "supported"
    assert claims[0]["evidence_ids"] == selected_ids
    assert len(model.events) == 1


@pytest.mark.parametrize("claim_date,source_date", [
    ("2026-10-07", "7 Oct 2026"),
    ("2026-10-07", "07 Oct2026"),
    ("2026年10月07日", "October 7, 2026"),
    ("7th October 2026", "2026-10-07"),
    ("2026-10-7", "2026年10月7号"),
    ("September 7, 2026", "7 Sept. 2026"),
    ("2026", "2026-10-07"),
])
def test_numeric_gate_accepts_equivalent_dates(claim_date, source_date):
    claim = Claim(id="C", text=f"Published {claim_date}.", evidence_ids=["E1"])
    assert deterministic_issue(claim, {"E1": row(text=f"Published {source_date}.")}) is None


@pytest.mark.parametrize("source", [
    "Published 7 October 2025.",
    "Published 10 July 2026.",
    "There were 2026 entries, 10 groups and 7 authors.",
])
def test_numeric_gate_preserves_complete_date_relationships(source):
    claim = Claim(id="C", text="Published 2026-10-07.", evidence_ids=["E1"])
    assert deterministic_issue(claim, {"E1": row(text=source)})


@pytest.mark.parametrize("claimed,observed,accepted", [
    ("007", "7", True),
    ("-007", "-7", True),
    ("007%", "7 %", True),
    ("-07", "7", False),
    ("7", "-07", False),
    ("20%", "20", False),
    ("20%", "0.20", False),
    ("2610.10310", "2610.1031", False),
    ("9 authors", "Alice, Bob, Carol, Dan, Eve, Fran, Gina, Henry and Ian.", False),
])
def test_numeric_gate_normalizes_leading_zeros_without_inventing_values(claimed, observed, accepted):
    claim = Claim(id="C", text=claimed, evidence_ids=["E1"])
    issue = deterministic_issue(claim, {"E1": row(text=observed)})
    assert (issue is None) is accepted


@pytest.mark.parametrize("field", ["title", "url"])
def test_numeric_gate_accepts_identifier_in_cited_source_metadata(field):
    source = {**row(text="A study of recursive self-improvement."), field: "https://arxiv.org/abs/2610.10310"}
    claim = Claim(id="C", text="The study is arXiv:2610.10310.", evidence_ids=["E1"])
    assert deterministic_issue(claim, {"E1": source}) is None
    # The same metadata cannot support a claim citing a different source.
    assert deterministic_issue(claim, {"E1": row(text="No identifier given."), "E2": source})


def test_metadata_number_match_does_not_bypass_semantic_checker():
    agent, model = make_agent([("verify", {"verdicts": [verdict(status="insufficient", quotes=[])]})])
    agent.add_evidence([{**row(text="A study of recursive self-improvement."),
                         "url": "https://arxiv.org/abs/2610.10310"}])
    claims, _ = agent.verify(Draft(claims=[Claim(id="C1", text="The study improved accuracy by 2610.10310%.", evidence_ids=["E1"])]))
    # Percent units still fail before the checker, even when the bare ID exists.
    assert claims[0]["status"] == "insufficient"
    assert model.events == []
    claims, _ = agent.verify(Draft(claims=[Claim(id="C1", text="The study had 2610.10310 participants.", evidence_ids=["E1"])]))
    assert claims[0]["status"] == "insufficient"
    assert [event["stage"] for event in model.events] == ["verify"]
    assert not model.script


@pytest.mark.parametrize("bad_verdict", [
    verdict(ids=[]),
    verdict(ids=["E99"]),
    verdict(quotes=[]),
    verdict(quotes=[""]),
    verdict(quotes=["London hosted the 2024 event."]),
    verdict(ids=["E1", "E1"], quotes=["Paris hosted the 2024 event."]),
])
def test_supported_requires_existing_cited_id_and_exact_nonempty_quote(bad_verdict):
    agent, _ = make_agent([("verify", {"verdicts": [bad_verdict]})])
    agent.add_evidence([row()])
    claims, _ = agent.verify(Draft(claims=[Claim(id="C1", text="Paris hosted the 2024 event.", evidence_ids=["E1"])]))
    assert claims[0]["status"] == "insufficient"


def test_omitted_checker_verdict_is_insufficient():
    agent, _ = make_agent([("verify", {"verdicts": []})])
    agent.add_evidence([row()])
    claims, _ = agent.verify(Draft(claims=[Claim(id="C1", text="Paris", evidence_ids=["E1"])]))
    assert claims[0]["status"] == "insufficient"
    assert "omitted" in claims[0]["reason"].lower()


def test_checker_cannot_switch_to_an_uncited_source():
    agent, _ = make_agent([("verify", {"verdicts": [verdict(ids=["E2"])]})])
    agent.add_evidence([row(), row("b")])
    claims, _ = agent.verify(Draft(claims=[Claim(id="C1", text="Paris", evidence_ids=["E1"])]))
    assert claims[0]["status"] == "insufficient"


def test_checker_subset_must_still_support_numerical_literals():
    agent, _ = make_agent([("verify", {"verdicts": [verdict(quotes=["The event took place in Paris."])]})])
    agent.add_evidence([row(text="The event took place in Paris."), row("b", "The event took place in 2024.")])
    claims, _ = agent.verify(Draft(claims=[Claim(id="C1", text="Paris hosted the 2024 event.", evidence_ids=["E1", "E2"])]))
    assert claims[0]["status"] == "insufficient"


@pytest.mark.parametrize("bad", [
    verdict(status="contradicted", ids=["E99"], quotes=["Fabricated quote"]),
    verdict(status="contradicted", ids=["E1"], quotes=["London hosted the event."]),
])
def test_contradiction_also_requires_real_quoted_evidence(bad):
    agent, _ = make_agent([("verify", {"verdicts": [bad]})])
    agent.add_evidence([row()])
    claims, _ = agent.verify(Draft(claims=[Claim(id="C1", text="London hosted the 2024 event.", evidence_ids=["E1"])]))
    assert claims[0]["status"] == "insufficient"


def test_answer_statement_must_contain_the_actual_answer():
    agent, model = make_agent()
    agent.add_evidence([row()])
    claims, _ = agent.verify(Draft(answer="London", answer_statement="Paris hosted the 2024 event.", answer_evidence_ids=["E1"]))
    assert claims[0]["id"] == "A0"
    assert claims[0]["status"] == "insufficient"
    assert model.events == []


def test_uncited_answer_cannot_be_smuggled_through_supported_side_claim():
    agent, _ = make_agent([
        ("plan", SEARCH), ("plan", {"done": True}),
        ("draft", {"answer": "London", "claims": [{"id": "C1", "text": "Paris hosted the 2024 event.", "evidence_ids": ["E1"]}]}),
        ("verify", {"verdicts": [verdict()]}),
    ], mode="verified_no_repair")
    result = agent.run()
    assert result["answer"] == ""
    assert result["claims"][0]["status"] == "insufficient"
    assert result["claims"][1]["status"] == "supported"
    assert result["repair_rounds"] == 0
    assert result["unresolved"]


def test_repair_is_triggered_for_missing_answer_even_without_candidate_claims():
    agent, model = make_agent([
        ("plan", SEARCH), ("plan", {"done": True}),
        ("draft", {"answer": "", "claims": [], "unresolved": ["Need the hosting city's name."]}),
        ("repair_plan", {"actions": [{"name": "semantic_search_files", "args": {"q": "event host announcement"}}]}),
        ("draft", {**ANSWER, "answer_evidence_ids": ["E2"]}),
        ("verify", {"verdicts": [verdict(claim_id="A0", ids=["E2"])]}),
    ], retriever=FakeRetriever([[row("a", "An event was held in 2024.")], [row("b")]]))
    result = agent.run()
    assert result["answer"] == "Paris"
    assert result["repair_rounds"] == 1
    assert result["tool_calls"] == 2
    assert not model.script


def test_repair_disabled_ablation_abstains_without_extra_retrieval():
    agent, _ = make_agent([
        ("plan", SEARCH), ("plan", {"done": True}),
        ("draft", {"answer": "", "claims": [], "unresolved": ["Missing evidence."]}),
    ], mode="verified_no_repair")
    result = agent.run()
    assert result["answer"] == ""
    assert result["repair_rounds"] == 0
    assert result["tool_calls"] == 1
    assert result["stop_reason"] != "completed"


def test_no_tools_baseline_does_not_retrieve_or_verify():
    retriever = FakeRetriever([AssertionError("Must never retrieve")])
    agent, model = make_agent([("draft", {"answer": "Paris"})], mode="no_tools", retriever=retriever)
    result = agent.run()
    assert result["answer"] == "Paris"
    assert retriever.calls == []
    assert result["tool_calls"] == result["rounds"] == 0
    assert result["evidence"] == []
    assert [event["stage"] for event in model.events] == ["draft"]
    assert model.payloads[0]["evidence"] == []


def test_single_rag_uses_one_retrieval_stage_and_no_checker():
    agent, model = make_agent([("draft", ANSWER)], mode="single_rag")
    result = agent.run()
    assert result["tool_calls"] == 1
    assert [event["stage"] for event in model.events] == ["draft"]
    assert all(c["status"] == "unverified" for c in result["claims"])


def test_repeated_successful_action_does_not_consume_tool_budget():
    agent, _ = make_agent()
    action = ToolAction(name="semantic_search_files", args={"q": "host city"})
    assert agent.execute(action)
    assert agent.execute(action) == []
    assert agent.tool_calls == 1
    assert agent.trace[-1]["status"] == "skipped_duplicate"


def test_transient_tool_failure_retries_once_and_counts_both_attempts():
    agent, _ = make_agent(retriever=FakeRetriever([TimeoutError("slow"), [row()]]))
    assert agent.execute(ToolAction(name="semantic_search_files", args={"q": "host city"}))
    assert agent.tool_calls == 2
    assert [t["status"] for t in agent.trace] == ["failed", "completed"]
    assert len(agent.evidence) == 1


def test_nontransient_tool_validation_failure_is_not_retried():
    retriever = FakeRetriever([ValueError("Query is invalid"), ValueError("Query is invalid")])
    agent, _ = make_agent(retriever=retriever)
    assert agent.execute(ToolAction(name="semantic_search_files", args={"q": "bad"})) == []
    assert agent.tool_calls == 1
    assert len(retriever.calls) == 1


def test_retry_does_not_exceed_retrieval_budget(monkeypatch):
    monkeypatch.setitem(config.LIMITS, "tool_calls", 1)
    agent, _ = make_agent(retriever=FakeRetriever([TimeoutError("slow"), [row()]]))
    assert agent.execute(ToolAction(name="semantic_search_files", args={"q": "host"})) == []
    assert agent.tool_calls == 1
    assert agent.stop_reason == "tool_budget"


def test_web_disabled_is_blocked_before_network_or_budget():
    agent, _ = make_agent(allow_web=False)
    assert agent.execute(ToolAction(name="read_webpage", args={"urls": ["https://example.org"], "query": "test"})) == []
    assert agent.tool_calls == 0
    assert agent.trace[-1]["status"] == "blocked"


def test_web_search_snippets_are_never_promoted_to_citable_evidence(monkeypatch):
    monkeypatch.setattr("app.agent.search_web", lambda *a, **k: [
        {"title": "Unopened page", "url": "https://example.org", "snippet": "Paris hosted the 2024 event.", "citable": False}
    ])
    agent, _ = make_agent(allow_web=True)
    observations = agent.execute(ToolAction(name="search_web", args={"query": "host city"}))
    assert observations[0]["snippet"]
    assert agent.evidence == {}
    assert agent.web_results


def test_second_round_web_discovery_is_opened_before_drafting(monkeypatch):
    monkeypatch.setattr("app.agent.search_web", lambda *a, **k: [
        {"title": "Announcement", "url": "https://example.org/event", "snippet": "A lead", "citable": False}
    ])
    monkeypatch.setattr("app.agent.read_webpage", lambda *a, **k: [row("web")])
    agent, model = make_agent([
        ("plan", SEARCH),
        ("plan", {"actions": [{"name": "search_web", "args": {"query": "event announcement"}}]}),
        ("plan", {"actions": [{"name": "read_webpage", "args": {"urls": ["https://example.org/event"]}}]}),
        ("plan", {"done": True}),
        ("draft", {**ANSWER, "answer_evidence_ids": ["E2"]}),
    ], mode="multi_step", allow_web=True, retriever=FakeRetriever([[row("a", "Unrelated teaching notes.")]]))
    result = agent.run()
    assert result["answer"] == "Paris"
    assert [t["tool"] for t in result["trace"]] == ["semantic_search_files", "search_web", "read_webpage"]
    assert len(result["evidence"]) == 2
    assert not model.script


def test_repair_discovery_is_opened_before_redrafting(monkeypatch):
    monkeypatch.setattr("app.agent.search_web", lambda *a, **k: [
        {"title": "Announcement", "url": "https://example.org/event", "snippet": "A lead", "citable": False}
    ])
    monkeypatch.setattr("app.agent.read_webpage", lambda *a, **k: [row("web")])
    agent, model = make_agent([
        ("plan", SEARCH), ("plan", {"done": True}),
        ("draft", {"answer": "", "unresolved": ["Missing the hosting city."]}),
        ("repair_plan", {"actions": [{"name": "search_web", "args": {"query": "event announcement"}}]}),
        ("repair_plan", {"actions": [{"name": "read_webpage", "args": {"urls": ["https://example.org/event"]}}]}),
        ("draft", {**ANSWER, "answer_evidence_ids": ["E2"]}),
        ("verify", {"verdicts": [verdict(claim_id="A0", ids=["E2"])]}),
    ], allow_web=True, retriever=FakeRetriever([[row("a", "Unrelated teaching notes.")]]))
    result = agent.run()
    assert result["answer"] == "Paris"
    assert result["repair_rounds"] == 2
    assert len(result["evidence"]) == 2
    assert not model.script


def test_repeated_web_leads_do_not_extend_discovery(monkeypatch):
    monkeypatch.setattr("app.agent.search_web", lambda *a, **k: [
        {"title": "Unopened page", "url": "https://example.org/event", "snippet": "A lead", "citable": False}
    ])
    agent, model = make_agent([
        ("plan", {"actions": [{"name": "search_web", "args": {"query": "event"}}]}),
        ("plan", {"actions": [{"name": "search_web", "args": {"query": "same event"}}]}),
        ("draft", {"answer": "", "unresolved": ["No source was opened."]}),
    ], mode="multi_step", allow_web=True)
    result = agent.run()
    assert result["answer"] == ""
    assert result["evidence"] == []
    assert result["stop_reason"] == "no_new_evidence"
    assert result["rounds"] == 2
    assert not model.script


def test_planner_receives_search_failure_details(monkeypatch):
    def unavailable(*a, **k):
        raise ValueError("Search provider returned no results")
    monkeypatch.setattr("app.agent.search_web", unavailable)
    agent, model = make_agent([("plan", {"done": True})], allow_web=True)
    agent.execute(ToolAction(name="search_web", args={"query": "unfamiliar topic"}))
    agent.decide()
    assert model.payloads[0]["prior_actions"][0]["error"] == "Search provider returned no results"


@pytest.mark.parametrize("arguments", [
    {"url": "https://example.org/event"},
    {"urls": "https://example.org/event"},
    {"urls": ["https://example.org/event"]},
])
def test_web_reader_accepts_single_url_forms_and_deduplicates(monkeypatch, arguments):
    opened = []
    def read(url, *a, **k):
        opened.append(url)
        return [row("web")]
    monkeypatch.setattr("app.agent.read_webpage", read)
    agent, _ = make_agent(allow_web=True)
    assert agent.execute(ToolAction(name="read_webpage", args=arguments))
    assert agent.execute(ToolAction(name="read_webpage", args={"urls": ["https://example.org/event"]})) == []
    assert opened == ["https://example.org/event"]
    assert agent.tool_calls == 1
    assert len(agent.evidence) == 1


def test_web_reader_rejects_multiple_urls_without_silently_dropping_one(monkeypatch):
    def must_not_read(*a, **k):
        raise AssertionError("Invalid multi-URL action must not call the network")
    monkeypatch.setattr("app.agent.read_webpage", must_not_read)
    agent, _ = make_agent(allow_web=True)
    assert agent.execute(ToolAction(name="read_webpage", args={"urls": ["https://a.example/", "https://b.example/"]})) == []
    assert agent.tool_calls == 1
    assert agent.trace[-1]["status"] == "failed"
    assert '"urls"' in agent.trace[-1]["error"]


def test_final_answer_in_exported_report_has_its_citation():
    agent, _ = make_agent([
        ("plan", SEARCH), ("plan", {"done": True}), ("draft", ANSWER),
        ("verify", {"verdicts": [verdict(claim_id="A0")]}),
    ], mode="verified_no_repair")
    result = agent.run()
    assert result["answer"] == "Paris"
    answer_section = result["report"].split("## Answer", 1)[1].split("## Supported findings", 1)[0]
    assert "Paris" in answer_section and "[E1]" in answer_section


def test_cancel_and_deadline_stop_before_any_tool_or_model_calls():
    agent, model = make_agent()
    agent.cancel.set()
    with pytest.raises(ModelError, match="Cancelled"):
        agent.execute(ToolAction(name="semantic_search_files", args={"q": "host"}))
    assert agent.stop_reason == "cancelled"
    assert not agent.retriever.calls and not model.events
    agent.cancel.clear()
    agent.deadline = time.monotonic() - 1
    with pytest.raises(ModelError, match="budget"):
        agent.check_budget()
    assert agent.stop_reason == "time_budget"


def test_initial_gathering_obeys_configured_decision_limit(monkeypatch):
    monkeypatch.setitem(config.LIMITS, "decision_rounds", 1)
    agent, model = make_agent([("plan", SEARCH), ("draft", ANSWER)], mode="multi_step")
    result = agent.run()
    assert result["rounds"] == 1
    assert len(model.events) == 2


def fake_http_client(monkeypatch, responses):
    pending = deque(responses)
    calls = []

    class FakeHTTP:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def post(self, url, **kwargs):
            calls.append(url)
            response = pending.popleft()
            if isinstance(response, Exception):
                raise response
            return response

    monkeypatch.setattr("app.llm.httpx.Client", FakeHTTP)
    monkeypatch.setattr(config, "API_KEY", "dummy-unit-test-key")
    return calls


def completion(content='{"answer":"Paris"}'):
    return httpx.Response(200, json={"model": "test-model", "usage": {"prompt_tokens": 42, "completion_tokens": 7},
        "choices": [{"finish_reason": "stop", "message": {"content": content}}]})


def test_model_transient_retry_counts_usage_and_unknown_failed_attempt(monkeypatch):
    calls = fake_http_client(monkeypatch, [httpx.Response(503, text="temporarily unavailable"), completion()])
    client = ModelClient(time.monotonic() + 60)
    result = client.structured("draft", "system", {}, Draft)
    assert result.answer == "Paris"
    assert len(calls) == client.usage["calls"] == 2
    assert client.usage["failed_attempts"] == 1
    assert client.usage["unknown_usage_attempts"] == 1
    assert client.usage["input_tokens"] == 42
    assert client.usage["output_tokens"] == 7


def test_model_invalid_json_does_not_silently_retry_or_fabricate(monkeypatch):
    calls = fake_http_client(monkeypatch, [completion("not json")])
    client = ModelClient(time.monotonic() + 60)
    with pytest.raises(ModelError):
        client.structured("draft", "system", {}, Draft)
    assert len(calls) == 1
    assert client.usage["failed_attempts"] == 1
    assert client.usage["input_tokens"] == 42


def test_failed_http_response_usage_is_counted_when_provider_returns_it(monkeypatch):
    fake_http_client(monkeypatch, [
        httpx.Response(429, json={"error": "rate limited after processing", "usage": {"prompt_tokens": 11, "completion_tokens": 3}}),
        completion(),
    ])
    client = ModelClient(time.monotonic() + 60)
    client.structured("draft", "system", {}, Draft)
    assert client.usage["input_tokens"] == 53
    assert client.usage["output_tokens"] == 10
    assert client.usage["unknown_usage_attempts"] == 0


def test_invalid_response_envelope_counts_unknown_usage(monkeypatch):
    fake_http_client(monkeypatch, [httpx.Response(200, json=[])])
    client = ModelClient(time.monotonic() + 60)
    with pytest.raises(ModelError):
        client.structured("draft", "system", {}, Draft)
    assert client.usage["calls"] == client.usage["failed_attempts"] == 1
    assert client.usage["unknown_usage_attempts"] == 1


@pytest.mark.parametrize("late_condition", ["time", "cancel"])
def test_late_model_result_cannot_become_success_after_limit(monkeypatch, late_condition):
    clock = {"now": 0.0, "cancelled": False}

    class LateResponse:
        status_code = 200

        def json(self):
            if late_condition == "time":
                clock["now"] = 11.0
            else:
                clock["cancelled"] = True
            return completion().json()

    fake_http_client(monkeypatch, [LateResponse()])
    monkeypatch.setattr("app.llm.time.monotonic", lambda: clock["now"])
    client = ModelClient(10.0, cancelled=lambda: clock["cancelled"])
    with pytest.raises(ModelError):
        client.structured("draft", "system", {}, Draft)
    # Even a discarded/late response consumed real model tokens.
    assert client.usage["input_tokens"] == 42
    assert client.usage["output_tokens"] == 7


def test_cost_estimate_uses_explicit_prices_and_date(monkeypatch):
    monkeypatch.setattr(config, "INPUT_PRICE", "2")
    monkeypatch.setattr(config, "OUTPUT_PRICE", "4")
    monkeypatch.setattr(config, "PRICING_DATE", "2026-11-16")
    client = ModelClient(time.monotonic() + 60)
    client.usage.update(input_tokens=1000, output_tokens=500, failed_attempts=1, unknown_usage_attempts=1)
    summary = client.usage_summary()
    assert summary["estimated_cost_usd"] == pytest.approx(.004)
    assert summary["pricing_date"] == "2026-11-16"
    assert "unknown-usage" in summary["cost_note"]


def test_model_retry_obeys_shared_call_cap(monkeypatch):
    monkeypatch.setitem(config.LIMITS, "model_calls", 1)
    calls = fake_http_client(monkeypatch, [httpx.Response(503, text="temporarily unavailable")])
    client = ModelClient(time.monotonic() + 60)
    with pytest.raises(ModelError, match="budget"):
        client.structured("draft", "system", {}, Draft)
    assert len(calls) == 1


def test_error_redaction_removes_configured_secret(monkeypatch):
    monkeypatch.setattr(config, "API_KEY", "unit-test-secret-never-real")
    assert "unit-test-secret-never-real" not in redact("Authorization unit-test-secret-never-real")
