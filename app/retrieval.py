from __future__ import annotations

import hashlib
import io
import re
import threading
import time
import zipfile
from collections import OrderedDict
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
from rank_bm25 import BM25Okapi
from .config import EMBEDDING_MODEL, MODELS, RETRIEVAL
from .khoj_core import markdown_sections
from .reranking import mixed_tokens, rerank, select_evidence

_model = None
_embedding_lock = threading.RLock()

def embedding_model():
    global _model
    with _embedding_lock:
        if _model is None:
            from fastembed import TextEmbedding
            _model = TextEmbedding(model_name=EMBEDDING_MODEL, cache_dir=str(MODELS), threads=2)
        return _model

def embed(texts, query=False):
    with _embedding_lock:
        model = embedding_model()
        result = list(model.query_embed(texts) if query else model.passage_embed(texts))
    arr = np.asarray(result, dtype=np.float32)
    if len(arr):
        arr /= np.maximum(np.linalg.norm(arr, axis=1, keepdims=True), 1e-12)
    return arr

def tokens(s):
    return re.findall(r"[\w]+|[\u4e00-\u9fff]", s.casefold())

def split_exact(text, max_chars=1000):
    """Bound input size, retain exact character spans; no invented sentence joins."""
    if sum(ord(c) > 127 for c in text) > len(text) * .25:
        max_chars = 400
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            cut = max(text.rfind("\n", start + max_chars // 2, end), text.rfind(" ", start + max_chars // 2, end))
            if cut > start:
                end = cut + 1
        if text[start:end].strip():
            yield start, end, text[start:end]
        start = end

def chunk_document(document):
    text, title = document["text"], document["title"]
    chunks = []
    if document.get("sentences") is not None:
        sentences = document["sentences"]
        for index, sentence in enumerate(sentences):
            sid = sentence.get("id", index) if isinstance(sentence, dict) else index
            content = sentence.get("text", "") if isinstance(sentence, dict) else sentence
            for start, end, fragment in split_exact(content):
                chunks.append({"text": fragment, "location": {"sentence_ids": [sid], "start_char": start, "end_char": end}})
    elif document.get("metadata", {}).get("pages"):
        for page in document["metadata"]["pages"]:
            for start, end, fragment in split_exact(page["text"]):
                chunks.append({"text": fragment, "location": {"page": page["page"], "start_char": start, "end_char": end}})
    else:
        for section in markdown_sections(text, title, max_words=160):
            for start, end, fragment in split_exact(section["text"]):
                line = section["start_line"] + section["text"][:start].count("\n")
                chunks.append({"text": fragment, "location": {"start_line": line,
                    "end_line": line + fragment.count("\n"), "section_start_char": start,
                    "section_end_char": end, "heading": section["heading"]}})
    return chunks

def decode_upload(filename, content):
    suffix = Path(filename).suffix.lower()
    metadata = {"filename": Path(filename).name}
    if suffix == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        if len(reader.pages) > 200:
            raise ValueError("PDF exceeds 200-page course-project limit")
        pages = [{"page": i + 1, "text": p.extract_text() or ""} for i, p in enumerate(reader.pages)]
        text = "\n\n".join(p["text"] for p in pages)
        metadata["pages"] = pages
    elif suffix == ".docx":
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            info = z.getinfo("word/document.xml")
            if info.file_size > 20_000_000:
                raise ValueError("DOCX expanded text is too large")
            root = ElementTree.fromstring(z.read(info))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        text = "\n".join("".join(t.text or "" for t in p.findall(".//w:t", ns)) for p in root.findall(".//w:p", ns))
    elif suffix in (".txt", ".md", ".markdown", ".html", ".htm"):
        text = content.decode("utf-8-sig", errors="replace")
        if suffix in (".html", ".htm"):
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(text, "html.parser")
            for node in soup(["script", "style", "nav"]):
                node.decompose()
            text = soup.get_text("\n", strip=True)
    else:
        raise ValueError("Supported files: TXT, Markdown, text PDF, DOCX and HTML")
    if not text.strip():
        raise ValueError("No readable text found; scanned PDFs require external OCR")
    if len(text) > 2_000_000:
        raise ValueError("Extracted document exceeds 2 million characters")
    return {"id": hashlib.sha256(filename.encode()).hexdigest()[:20],
            "title": Path(filename).name, "text": text, "metadata": metadata}

class Retriever:
    def __init__(self, store, settings=RETRIEVAL, *, max_cached_collections=8):
        if max_cached_collections < 1:
            raise ValueError("max_cached_collections must be positive")
        self.store = store
        self.settings = settings
        self.cache = OrderedDict()
        self.max_cached_collections = max_cached_collections
        self._index_lock = threading.RLock()

    def ingest(self, cid, document):
        if not self.store.collection_exists(cid):
            raise ValueError("Collection not found")
        existing = self.store.existing_document(cid, document)
        if existing:
            return existing
        chunks = chunk_document(document)
        if not chunks:
            if document.get("sentences") == []:
                return self._save(cid, document, [], [])
            raise ValueError("No nonempty source passages")
        if len(chunks) > 5000:
            raise ValueError("Document exceeds 5000 passages")
        vectors = embed([document["title"][:150] + "\n" + c["text"] for c in chunks])
        return self._save(cid, document, chunks, vectors)

    def _save(self, cid, document, chunks, vectors):
        with self._index_lock:
            result = self.store.save_document(cid, document, chunks, vectors)
            self.cache.pop(cid, None)
            return result

    def _index(self, cid, tokenize):
        with self._index_lock:
            cached = self.cache.get(cid)
            if cached is None or cached[0] is not tokenize:
                rows = self.store.chunks(cid)
                if not rows:
                    return None
                vectors = np.stack([np.frombuffer(r.pop("vector"), dtype=np.float32) for r in rows])
                bm25 = BM25Okapi([tokenize(r["title"] + " " + r["text"]) or ["_"] for r in rows])
                cached = (tokenize, (rows, vectors, bm25))
                self.cache[cid] = cached
            self.cache.move_to_end(cid)
            while len(self.cache) > self.max_cached_collections:
                self.cache.popitem(last=False)
            return cached[1]

    def search(self, cid, query, top_k=6, *, diagnostics=None):
        if not str(query).strip():
            raise ValueError("Search query cannot be empty")
        if top_k < 0:
            raise ValueError("top_k must be nonnegative")
        settings = self.settings
        enhanced = settings.mode == "enhanced"
        tokenize = mixed_tokens if enhanced else tokens
        trace = diagnostics if diagnostics is not None else {}
        trace.update(settings.describe(), candidate_count=0, rerank_ms=0)
        if top_k == 0:
            return []
        index = self._index(cid, tokenize)
        if index is None:
            return []
        rows, vectors, bm25 = index
        q = embed([query], query=True)[0]
        dense = vectors @ q
        sparse = bm25.get_scores(tokenize(query))
        score = np.zeros(len(rows))
        pool_size = settings.candidates if enhanced else top_k
        depth = max(30, pool_size)
        for scores in (dense, sparse):
            for rank, idx in enumerate(np.argsort(-scores, kind="stable")[:depth]):
                score[idx] += 1 / (60 + rank + 1)
        selected = np.argsort(-score, kind="stable")[:pool_size]
        candidates = [dict({k: v for k, v in rows[i].items() if k != "vector"},
                           score=float(score[i]), semantic_score=float(dense[i])) for i in selected]
        trace["candidate_count"] = len(candidates)
        if not enhanced:
            return candidates
        started = time.perf_counter()
        try:
            ranked = rerank(query, candidates, bm25.idf)
            return select_evidence(ranked, top_k, settings.diversity_margin)
        finally:
            trace["rerank_ms"] = round((time.perf_counter() - started) * 1000, 3)

    def read_file(self, cid, path, start_line=None, end_line=None):
        # Paths are corpus IDs/titles, never arbitrary filesystem paths.
        candidates = self.store.document_chunks(cid, path, match_title=True)
        if start_line is not None:
            end_line = min(end_line or start_line + 49, start_line + 49)
            candidates = [r for r in candidates if r["location"].get("end_line", 10**9) >= start_line
                          and r["location"].get("start_line", 0) <= end_line]
        candidates.sort(key=lambda r: (r["location"].get("page", 0),r["location"].get("start_line", 0),
            min(r["location"].get("sentence_ids", [0])),
            r["location"].get("start_char", r["location"].get("section_start_char", 0)), r["id"]))
        return [{k: v for k, v in r.items() if k != "vector"} for r in candidates[:8]]
