from __future__ import annotations

import hashlib
import ipaddress
import socket
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup

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

def search_web(query, timeout=15):
    from ddgs import DDGS
    with DDGS(timeout=max(1, min(15, int(timeout)))) as engine:
        rows = list(engine.text(query, max_results=5))
    return [{"title": r.get("title", ""), "url": r.get("href", r.get("url", "")),
             "snippet": r.get("body", ""), "citable": False} for r in rows]

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
