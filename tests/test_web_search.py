"""Search recovery tests use fake providers; no network or generation model."""
import json
import subprocess
from types import SimpleNamespace

import pytest

from app import web_tools as web


def sample(url="https://example.org/paper"):
    return {"title": "Example paper", "url": url, "snippet": "A discovery snippet", "citable": True}


def test_primary_success_does_not_call_fallback_and_keeps_query(monkeypatch):
    seen = []
    query = '  original "quoted" query; no rewrite  '
    def provider(name, q, timeout):
        seen.append((name, q, timeout))
        return {"rows": [sample()], "status": "completed"}
    monkeypatch.setattr(web, "_run_search_provider", provider)
    rows = web.search_web(query)
    assert len(seen) == 1 and seen[0][1] == query
    assert rows[0]["provider"] == "ddgs_auto"
    assert rows[0]["search_query"] == query
    assert rows[0]["citable"] is False
    assert rows[0]["search_attempts"][0]["status"] == "completed"


def test_unavailable_primary_uses_scoped_fallback_with_diagnostics(monkeypatch):
    seen = []
    def provider(name, query, timeout):
        seen.append(name)
        return ({"rows": [], "status": "empty_or_unavailable", "error": "Provider returned no parseable results"}
                if name == "ddgs_auto" else {"rows": [sample()], "status": "completed"})
    monkeypatch.setattr(web, "_run_search_provider", provider)
    rows = web.search_web("a research question")
    assert seen == ["ddgs_auto", "arxiv_search"]
    assert rows[0]["provider"] == "arxiv_search"
    assert "not a general web index" in rows[0]["provider_scope"]
    assert [a["status"] for a in rows[0]["search_attempts"]] == ["empty_or_unavailable", "completed"]
    assert rows[0]["citable"] is False


def test_empty_both_providers_does_not_claim_information_is_absent(monkeypatch):
    monkeypatch.setattr(web, "_run_search_provider", lambda *a: {"rows": [], "status": "no_results"})
    with pytest.raises(web.WebSearchError) as captured:
        web.search_web("unmatched phrase")
    assert len(captured.value.search_attempts) == 2
    assert "does not establish" in str(captured.value)
    assert "arXiv papers only" in str(captured.value)


def test_provider_failure_never_exposes_raw_proxy_credentials(monkeypatch):
    def fail(*args):
        raise ConnectionError("proxy https://alice:SUPER_SECRET@example.org failed")
    monkeypatch.setattr(web, "_run_search_provider", fail)
    with pytest.raises(web.WebSearchError) as captured:
        web.search_web("query")
    assert "SUPER_SECRET" not in str(captured.value)
    assert "SUPER_SECRET" not in json.dumps(captured.value.search_attempts)
    assert all(a["status"] == "network_error" for a in captured.value.search_attempts)


def test_all_provider_attempts_share_total_wall_clock_budget(monkeypatch):
    clock, allocations = {"now": 0.0}, []
    monkeypatch.setattr(web.time, "monotonic", lambda: clock["now"])
    def timeout(name, query, allowance):
        allocations.append(allowance)
        clock["now"] += allowance
        raise TimeoutError("slow provider")
    monkeypatch.setattr(web, "_run_search_provider", timeout)
    with pytest.raises(web.WebSearchTimeout) as captured:
        web.search_web("query", timeout=15)
    assert len(allocations) == 2
    assert sum(allocations) == pytest.approx(15)
    assert allocations[0] <= 7
    assert len(captured.value.search_attempts) == 2


def test_subsecond_remaining_budget_is_not_rounded_up(monkeypatch):
    clock, allocations = {"now": 0.0}, []
    monkeypatch.setattr(web.time, "monotonic", lambda: clock["now"])
    def timeout(name, query, allowance):
        allocations.append(allowance)
        clock["now"] += allowance
        raise TimeoutError("slow provider")
    monkeypatch.setattr(web, "_run_search_provider", timeout)
    with pytest.raises(web.WebSearchTimeout):
        web.search_web("query", timeout=.1)
    assert sum(allocations) == pytest.approx(.1)
    assert all(a < .1 for a in allocations)


def test_late_result_is_discarded_instead_of_reported_as_success(monkeypatch):
    clock = {"now": 0.0}
    monkeypatch.setattr(web.time, "monotonic", lambda: clock["now"])
    def late(*args):
        clock["now"] = 16
        return {"rows": [sample()], "status": "completed"}
    monkeypatch.setattr(web, "_run_search_provider", late)
    with pytest.raises(web.WebSearchTimeout) as captured:
        web.search_web("query", timeout=15)
    assert captured.value.search_attempts[0]["status"] == "deadline_exceeded"
    assert captured.value.search_attempts[0]["discarded_results"] == 1


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_time_budget_does_not_start_worker(monkeypatch, timeout):
    monkeypatch.setattr(web, "_run_search_provider", lambda *a: pytest.fail("must not start"))
    with pytest.raises(web.WebSearchTimeout):
        web.search_web("query", timeout=timeout)


def test_hidden_worker_receives_query_via_stdin_and_has_hard_timeout(monkeypatch):
    recorded = {}
    query = 'topic; $(not-shell-code) 中文'
    def fake_run(args, **kwargs):
        recorded.update(args=args, **kwargs)
        return SimpleNamespace(returncode=0, stdout='{"rows":[],"status":"no_results"}')
    monkeypatch.setattr(web.subprocess, "run", fake_run)
    web._run_search_provider("arxiv_search", query, 1.25)
    assert query not in recorded["args"]
    assert json.loads(recorded["input"])["query"] == query
    assert recorded["timeout"] == 1.25
    assert recorded["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)
    assert recorded.get("shell", False) is False


def test_worker_timeout_surfaces_as_timeout_without_stderr_secrets(monkeypatch):
    def fail(*a, **k):
        raise subprocess.TimeoutExpired("worker", 1, stderr="PRIVATE_PROXY_SECRET")
    monkeypatch.setattr(web.subprocess, "run", fail)
    with pytest.raises(TimeoutError) as captured:
        web._run_search_provider("ddgs_auto", "query", 1)
    assert "PRIVATE_PROXY_SECRET" not in str(captured.value)


def test_result_validation_deduplicates_urls_and_never_accepts_citable_flag():
    rows = web._normalize_search_rows([
        sample(), sample(), sample("javascript:alert(1)"),
        sample("https://user:password@example.org"), None,
    ])
    assert len(rows) == 1
    assert rows[0]["citable"] is False


def fake_search_page(monkeypatch, html):
    seen = []
    class Page:
        encoding = "utf-8"
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def raise_for_status(self): pass
        def iter_bytes(self): yield html.encode()
    class Client:
        def __init__(self, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def stream(self, method, url, **kwargs):
            seen.append((method, url, kwargs))
            return Page()
    monkeypatch.setattr(web.httpx, "Client", Client)
    return seen


def test_arxiv_fallback_parses_original_query_and_abstract_without_controls(monkeypatch):
    seen = fake_search_page(monkeypatch, '''<ol><li class="arxiv-result">
      <p class="list-title"><a href="https://arxiv.org/abs/9999.12345">ID</a></p>
      <p class="title">Example paper</p><p class="abstract"><span class="abstract-full">A scholarly summary.<a>Less</a></span></p>
    </li></ol>''')
    query = "Unmodified scholarly query"
    rows = web._arxiv_search(query, 3)
    assert rows[0]["title"] == "Example paper"
    assert rows[0]["snippet"] == "A scholarly summary."
    assert seen[0][2]["params"]["query"] == query


def test_arxiv_explicit_empty_page_is_distinct_from_parser_or_challenge_failure(monkeypatch):
    fake_search_page(monkeypatch, "<h1>Sorry, your query returned no results.</h1>")
    assert web._arxiv_search("query", 3) == []
    fake_search_page(monkeypatch, "<h1>Confirm that you are human</h1>")
    with pytest.raises(ValueError, match="recognized results"):
        web._arxiv_search("query", 3)
