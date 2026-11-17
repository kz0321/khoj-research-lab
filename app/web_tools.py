from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import math
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
SEARCH_PROVIDERS = ("ddgs_auto", "arxiv_search")
SEARCH_SCOPES = {"ddgs_auto": "general web metasearch",
                 "arxiv_search": "arXiv scholarly papers; not a general web index"}
SEARCH_MAX_SECONDS = 15.0


class WebSearchError(RuntimeError):
    """Search failed without implying that the requested information is absent."""
    def __init__(self, message, attempts):
        super().__init__(message)
        self.search_attempts = attempts


class WebSearchTimeout(TimeoutError):
    def __init__(self, message, attempts):
        super().__init__(message)
        self.search_attempts = attempts

def validate_public_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public HTTP(S) URLs without credentials are allowed")
    if parsed.port not in (None, 80, 443):
        raise ValueError("Nonstandard web ports are blocked")
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError("Private, loopback and reserved network addresses are blocked")
    return url

def _search_error(error):
    """Expose useful failure categories, never raw proxy URLs or credentials."""
    if isinstance(error, (TimeoutError, httpx.TimeoutException)) or "timeout" in type(error).__name__.lower():
        return {"status": "timeout", "error": "Provider request timed out."}
    if isinstance(error, httpx.HTTPStatusError):
        return {"status": "http_error", "error": f"Provider HTTP {error.response.status_code}."}
    if "no results found" in str(error).lower():
        return {"status": "empty_or_unavailable", "error": "No parseable results; provider blocking or parser changes can also cause this."}
    if isinstance(error, (httpx.NetworkError, ConnectionError, OSError)):
        return {"status": "network_error", "error": "Provider connection failed."}
    return {"status": "provider_error", "error": f"Provider failed ({type(error).__name__})."}


def _arxiv_search(query, timeout):
    # Same query, explicitly scoped academic fallback; no topic-specific rewrite.
    with httpx.Client(timeout=max(.05, min(8.0, timeout)), follow_redirects=False,
                      headers={"User-Agent": "KhojResearchLab/1.0 (educational literature search)"}) as client:
        with client.stream("GET", "https://arxiv.org/search/", params={
            "query": query, "searchtype": "all", "abstracts": "show",
            "order": "-announced_date_first", "size": 50,
        }) as response:
            response.raise_for_status()
            body = bytearray()
            for block in response.iter_bytes():
                body.extend(block)
                if len(body) > 2_000_000:
                    raise ValueError("Search response exceeds size limit")
            html = bytes(body).decode(response.encoding or "utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    items = soup.select("li.arxiv-result")
    rows = []
    for item in items[:5]:
        title, link = item.select_one("p.title"), item.select_one("p.list-title a[href]")
        abstract = item.select_one(".abstract-full") or item.select_one("p.abstract")
        if not title or not link:
            continue
        if abstract:
            for control in abstract.select("a, .is-hidden"):
                control.decompose()
        rows.append({"title": title.get_text(" ", strip=True), "url": link["href"],
                     "snippet": abstract.get_text(" ", strip=True) if abstract else ""})
    if not rows:
        text = soup.get_text(" ", strip=True).lower()
        if not any(marker in text for marker in ("no results", "0 results", "sorry, your query", "did not match any")):
            raise ValueError("Search page has no recognized results or explicit empty-result marker")
    return rows


def _provider_search(provider, query, timeout):
    if provider == "ddgs_auto":
        from ddgs import DDGS
        with DDGS(timeout=max(1, min(5, int(timeout)))) as engine:
            return list(engine.text(query, backend="auto", max_results=5))
    if provider == "arxiv_search":
        return _arxiv_search(query, timeout)
    raise ValueError("Unknown search provider")


def _normalize_search_rows(rows):
    clean, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = row.get("href", row.get("url", ""))
        if not isinstance(url, str) or len(url) > 4096:
            continue
        try:
            parsed = urlparse(url)
            valid = parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username and not parsed.password
        except ValueError:
            valid = False
        if not valid or url in seen:
            continue
        seen.add(url)
        clean.append({"title": str(row.get("title", ""))[:500], "url": url,
                      "snippet": str(row.get("body", row.get("snippet", "")))[:1800], "citable": False})
        if len(clean) >= 5:
            break
    return clean


def _run_search_provider(provider, query, timeout):
    """Bound the whole call, including DDGS thread-pool shutdown, on Windows.

    HTTP timeouts alone are per operation; DDGS can wait for several futures.
    A short-lived hidden process can be killed without leaking search threads.
    No model client/config is imported by the worker, and queries travel on stdin.
    """
    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.web_tools", "--search-worker", provider],
            input=json.dumps({"query": query, "timeout": timeout}, ensure_ascii=False),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=str(Path(__file__).resolve().parent.parent), timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        # subprocess.run kills and waits for its own child on timeout.
        raise TimeoutError("Search provider exceeded its wall-clock allocation") from None
    if result.returncode:
        raise RuntimeError("Search provider process failed")
    try:
        outcome = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise RuntimeError("Search provider returned invalid structured output") from None
    if not isinstance(outcome, dict) or not isinstance(outcome.get("rows"), list):
        raise RuntimeError("Search provider returned invalid structured output")
    return outcome


def search_web(query, timeout=15):
    if not isinstance(query, str) or not query.strip() or len(query) > 3000:
        raise ValueError("Search query must contain 1-3000 characters")
    timeout = float(timeout)
    if not math.isfinite(timeout) or timeout <= 0:
        raise WebSearchTimeout("No remaining web-search time budget", [])
    deadline = time.monotonic() + min(timeout, SEARCH_MAX_SECONDS)
    attempts = []
    for index, provider in enumerate(SEARCH_PROVIDERS):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        # Reserve time for a distinct backend rather than repeatedly retrying an
        # unavailable metasearch source. The query is preserved verbatim.
        allocation = min(7.0, remaining * .55) if index == 0 else remaining
        begin = time.monotonic()
        try:
            outcome = _run_search_provider(provider, query, allocation)
            rows = _normalize_search_rows(outcome["rows"])
            status = "completed" if rows else outcome.get("status", "no_results")
            attempt = {"provider": provider, "status": status,
                       "elapsed_seconds": round(time.monotonic() - begin, 3), "results": len(rows)}
            if outcome.get("error"):
                attempt["error"] = outcome["error"]
        except Exception as error:
            rows = []
            attempt = {"provider": provider, **_search_error(error), "results": 0,
                       "elapsed_seconds": round(time.monotonic() - begin, 3)}
        attempts.append(attempt)
        logger.info("Web search provider %s: %s (%.3fs)", provider, attempt["status"], attempt["elapsed_seconds"])
        if time.monotonic() >= deadline:
            if rows:
                attempt.update(status="deadline_exceeded", discarded_results=len(rows))
            break
        if rows:
            for row in rows:
                row.update(provider=provider, provider_scope=SEARCH_SCOPES[provider], search_query=query)
            # Retained in tool observations/export; it is diagnostic metadata,
            # not a fabricated evidence passage or an extra search result.
            rows[0]["search_attempts"] = list(attempts)
            return rows
    summary = "; ".join(f"{a['provider']}={a['status']}" for a in attempts)
    message = "Web search found no usable results from the configured providers (" + summary + "). This does not establish that no relevant work exists. The fallback covers arXiv papers only."
    if time.monotonic() >= deadline:
        raise WebSearchTimeout(message + " Shared search deadline exhausted.", attempts)
    raise WebSearchError(message, attempts)


def _search_worker():
    if len(sys.argv) != 3 or sys.argv[1] != "--search-worker" or sys.argv[2] not in SEARCH_PROVIDERS:
        raise SystemExit("Internal search worker requires a configured provider")
    try:
        request = json.loads(sys.stdin.buffer.read())
        rows = _normalize_search_rows(_provider_search(sys.argv[2], request["query"], request["timeout"]))
        result = {"rows": rows, "status": "completed" if rows else "no_results"}
    except Exception as error:
        result = {"rows": [], **_search_error(error)}
    # ASCII JSON also works when a Windows console defaults to a legacy codepage.
    print(json.dumps(result, ensure_ascii=True))

def read_webpage(url, query="", timeout=20):
    # Revalidate every redirect; search snippets are never promoted to evidence.
    target = validate_public_url(url)
    with httpx.Client(timeout=max(1, min(20, timeout)), follow_redirects=False,
                      headers={"User-Agent": "KhojResearchLab/1.0 (educational evidence research)"}) as client:
        for _ in range(4):
            with client.stream("GET", target) as response:
                if response.is_redirect:
                    target = validate_public_url(urljoin(target, response.headers["location"]))
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "html" not in content_type and "text/plain" not in content_type:
                    raise ValueError("Web reader supports HTML/plain text; import PDF files locally")
                body = bytearray()
                for block in response.iter_bytes():
                    body.extend(block)
                    if len(body) > 2_000_000:
                        raise ValueError("Web page exceeds 2 MB")
                html = bytes(body).decode(response.encoding or "utf-8", errors="replace")
                break
        else:
            raise ValueError("Too many redirects")
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(strip=True) if soup.title else target
    for el in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        el.decompose()
    text = soup.get_text("\n", strip=True)
    from .retrieval import split_exact, tokens
    fragments = list(split_exact(text))
    q = set(tokens(query))
    ranked = sorted(enumerate(fragments), key=lambda item: -len(q.intersection(tokens(item[1][2]))))[:6]
    digest = hashlib.sha256(text.encode()).hexdigest()
    return [{"id": hashlib.sha256(f'{target}:{digest}:{i}'.encode()).hexdigest()[:24],
             "source_id": target, "title": title, "text": fragment,
             "url": target, "location": {"start_char": start, "end_char": end},
             "retrieved_at": datetime.now(timezone.utc).isoformat(), "source_sha256": digest,
             "source_snapshot": text}
            for i, (start, end, fragment) in ranked]


if __name__ == "__main__":
    _search_worker()
