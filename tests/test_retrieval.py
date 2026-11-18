"""Isolated retrieval, source provenance and web-boundary behavior tests."""
import io
import socket

import numpy as np
import pytest

from app import retrieval, web_tools
from app.config import RetrievalSettings
from app.reranking import mixed_tokens, rerank, select_evidence
from app.retrieval import Retriever, chunk_document, decode_upload, split_exact
from app.store import Store


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    def fake_embed(texts, query=False):
        # Explicitly fake embeddings: test storage/ranking boundaries, not
        # semantic-model quality or public-benchmark scores.
        vectors = []
        for text in texts:
            lower = text.lower()
            v = np.array([lower.count("alpha") + .1, lower.count("beta") + .1, .1], dtype=np.float32)
            vectors.append(v / np.linalg.norm(v))
        return np.asarray(vectors, dtype=np.float32)

    monkeypatch.setattr(retrieval, "embed", fake_embed)
    store = Store(tmp_path / "research.sqlite3")
    store.create_collection("Dataset A", "a")
    store.create_collection("Dataset B", "b")
    return store, Retriever(store)


def test_search_and_read_file_cannot_cross_collection_boundary(corpus):
    store, retriever = corpus
    retriever.ingest("a", {"id": "shared-id", "title": "Shared title", "text": "alpha public source"})
    retriever.ingest("b", {"id": "shared-id", "title": "Shared title", "text": "beta held-out secret"})
    for result in (retriever.search("a", "beta held-out secret"), retriever.read_file("a", "shared-id"), retriever.read_file("a", "Shared title")):
        assert result
        assert all(r["collection_id"] == "a" for r in result)
        assert all("secret" not in r["text"] for r in result)
    assert set(r["id"] for r in store.chunks("a")).isdisjoint(r["id"] for r in store.chunks("b"))


def test_empty_collection_returns_no_evidence(corpus):
    _, retriever = corpus
    assert retriever.search("a", "alpha") == []
    assert retriever.read_file("a", "C:\\Windows\\system.ini") == []


def test_mixed_query_shares_terms_with_unspaced_chinese_passage():
    query = mixed_tokens("香港AI2026")
    assert query == ["香", "港", "香港", "ai2026"]
    passage = mixed_tokens("介紹香港AI2026模型")
    assert set(query) <= set(passage)
    assert mixed_tokens("naïve GPT_4, v2.1") == ["naïve", "gpt_4", "v2", "1"]
    assert retrieval.tokens("香港AI2026") == ["香港ai2026"]


def test_reranker_rewards_matching_phrase_over_scattered_words():
    rows = [{"id": "scattered", "title": "", "text": "delta unrelated beta"},
            {"id": "phrase", "title": "", "text": "the delta beta study"}]
    ranked = rerank("delta beta", rows, {})
    assert [row["id"] for row in ranked] == ["phrase", "scattered"]


def test_diversity_only_promotes_close_matches_and_keeps_complementary_evidence():
    def item(key, source, text, score, lexical=1):
        return dict(id=key, source_id=source, text=text, rerank_score=score, lexical_score=lexical)

    ranked = [item("1", "a", "fact one", .99), item("2", "a", "fact two", .88),
              item("3", "b", "fact  one", .87), item("4", "c", "no match", .86, 0),
              item("5", "b", "fact three", .85), item("6", "d", "weak match", .4)]
    assert [r["id"] for r in select_evidence(ranked, 3, .04)] == ["1", "5", "2"]
    assert [r["id"] for r in select_evidence(ranked, 2, .01)] == ["1", "2"]
    assert [r["id"] for r in select_evidence(ranked, 2, 0)] == ["1", "2"]


def test_enhanced_pipeline_uses_bounded_pool_and_preserves_citations(corpus):
    store, _ = corpus
    enhanced = Retriever(store, RetrievalSettings("enhanced", candidates=6))
    for i in range(9):
        enhanced.ingest("a", {"id": str(i), "title": "Record", "text": "alpha 重复"})
    enhanced.ingest("b", {"id": "0", "title": "Record", "text": "alpha private"})
    trace = {}
    result = enhanced.search("a", "重复", top_k=8, diagnostics=trace)
    assert trace["candidate_count"] == 6
    assert trace["rerank_ms"] >= 0
    assert len(result) == 1
    hit = result[0]
    original = next(r for r in store.chunks("a") if r["id"] == hit["id"])
    for field in ("collection_id", "source_id", "location", "text", "id"):
        assert hit[field] == original[field]
    enhanced.ingest("a", {"id": hit["source_id"], "title": "Record", "text": "alpha 正确版本"})
    assert enhanced.search("a", "正确版本")[0]["text"] == "alpha 正确版本"
    assert enhanced.search("a", "alpha", top_k=0) == []
    with pytest.raises(ValueError, match="nonnegative"):
        enhanced.search("a", "alpha", top_k=-1)


def test_baseline_keeps_rrf_scores_tie_order_and_duplicates(corpus, monkeypatch):
    store, _ = corpus
    baseline = Retriever(store, RetrievalSettings("baseline"))
    def unexpected(*args):
        pytest.fail("The baseline must bypass the enhanced scorer")
    monkeypatch.setattr(retrieval, "rerank", unexpected)
    for i in range(4):
        baseline.ingest("a", {"id": str(i), "title": "Record", "text": "alpha 重复"})
    rows = baseline.search("a", "alpha", top_k=3)
    assert [r["id"] for r in rows] == [r["id"] for r in store.chunks("a")[:3]]
    assert [r["score"] for r in rows] == pytest.approx([2 / 61, 2 / 62, 2 / 63])
    assert all("rerank_score" not in r for r in rows)


def test_reranker_failure_is_visible(corpus, monkeypatch):
    store, _ = corpus
    enhanced = Retriever(store, RetrievalSettings("enhanced"))
    enhanced.ingest("a", {"id": "a", "title": "Record", "text": "alpha"})
    def fail(*args):
        raise RuntimeError("scoring failed")
    monkeypatch.setattr(retrieval, "rerank", fail)
    with pytest.raises(RuntimeError, match="scoring failed"):
        enhanced.search("a", "alpha")


def test_retrieval_metrics_require_gold_sentences_and_count_duplicate_slots():
    from eval.compare_retrieval import score

    def hit(source, sentence, text):
        return {"source_id": source, "location": {"sentence_ids": [sentence]}, "text": text}

    rows = [hit("a", 1, "unrelated"), hit("b", 2, "fact"), hit("b", 2, "fact")]
    assert score(rows, [["a", 0], ["b", 2]]) == pytest.approx({
        "recall_at_6": 0.5, "reciprocal_rank_at_6": 0.5,
        "relevant_source_coverage": 0.5, "duplicate_fraction": 1 / 3,
    })


def test_document_replacement_invalidates_cached_retrieval(corpus):
    _, retriever = corpus
    retriever.ingest("a", {"id": "d", "title": "Alpha", "text": "alpha old version"})
    old = retriever.search("a", "alpha")[0]
    retriever.ingest("a", {"id": "d", "title": "Alpha", "text": "alpha corrected version"})
    new = retriever.search("a", "alpha")[0]
    assert new["id"] != old["id"]
    assert "corrected" in new["text"] and "old version" not in new["text"]


def test_chunk_identity_changes_if_sentence_locations_change(corpus):
    store, retriever = corpus
    retriever.ingest("a", {"id": "d", "title": "Alpha", "text": "alpha evidence", "sentences": [{"id": 3, "text": "alpha evidence"}]})
    old = store.chunks("a")[0]
    retriever.ingest("a", {"id": "d", "title": "Alpha", "text": "alpha evidence", "sentences": [{"id": 7, "text": "alpha evidence"}]})
    new = store.chunks("a")[0]
    assert old["location"] != new["location"]
    assert old["id"] != new["id"], "Chunk ID must identify both content and its citable source location"


def test_sentence_ids_survive_fragmentation_and_withheld_gaps():
    sentences = [{"id": 0, "text": "alpha " * 260}, {"id": 4, "text": "beta fact"}]
    chunks = chunk_document({"title": "Facts", "text": "alpha beta", "sentences": sentences})
    assert len(chunks) > 2
    assert {s for chunk in chunks for s in chunk["location"]["sentence_ids"]} == {0, 4}
    lookup = {s["id"]: s["text"] for s in sentences}
    for chunk in chunks:
        location = chunk["location"]
        assert lookup[location["sentence_ids"][0]][location["start_char"]:location["end_char"]] == chunk["text"]


def test_pdf_page_provenance_is_not_flattened():
    document = {"title": "Paper", "text": "first\nsecond", "metadata": {"pages": [
        {"page": 1, "text": "First page fact"}, {"page": 2, "text": "Second page fact"}]}}
    chunks = chunk_document(document)
    assert [(c["location"]["page"], c["text"]) for c in chunks] == [(1, "First page fact"), (2, "Second page fact")]


def test_real_pdf_bytes_extract_with_page_and_exact_passage_locations():
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

    writer = PdfWriter()
    for literal in ("Alpha fact on first page.", "Beta fact on second page."):
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"):
            DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({literal}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    buffer = io.BytesIO()
    writer.write(buffer)
    document = decode_upload("two-page.pdf", buffer.getvalue())
    assert len(document["metadata"]["pages"]) == 2
    chunks = chunk_document(document)
    assert {c["location"]["page"] for c in chunks} == {1, 2}
    pages = {p["page"]: p["text"] for p in document["metadata"]["pages"]}
    for chunk in chunks:
        loc = chunk["location"]
        assert pages[loc["page"]][loc["start_char"]:loc["end_char"]] == chunk["text"]
    assert "Alpha fact" in chunks[0]["text"]
    assert "Beta fact" in chunks[1]["text"]


def test_image_only_or_blank_pdf_does_not_silently_import_empty_evidence():
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(ValueError, match="No readable text"):
        decode_upload("scanned.pdf", buffer.getvalue())


def test_split_exact_retains_characters_and_unicode_offsets():
    text = ("原始证据与数字 2024。" * 100) + "\nLast line."
    fragments = list(split_exact(text))
    assert "".join(fragment for _, _, fragment in fragments) == text
    for start, end, fragment in fragments:
        assert text[start:end] == fragment
        assert end - start <= 400


def test_html_ingestion_excludes_scripts_and_keeps_readable_evidence():
    document = decode_upload("paper.html", b"<title>Paper</title><script>secret injection()</script><p>Visible fact.</p>")
    assert "Visible fact." in document["text"]
    assert "secret" not in document["text"]


def test_empty_or_unsupported_upload_is_explicit_error():
    with pytest.raises(ValueError, match="No readable"):
        decode_upload("empty.txt", b" \n")
    with pytest.raises(ValueError, match="Supported files"):
        decode_upload("archive.exe", b"binary")


def address(ip):
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return [(family, socket.SOCK_STREAM, 6, "", (ip, 443))]


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.169.254", "::1", "fc00::1"])
def test_web_reader_rejects_nonpublic_dns_resolution(monkeypatch, ip):
    monkeypatch.setattr(web_tools.socket, "getaddrinfo", lambda *a, **k: address(ip))
    with pytest.raises(ValueError, match="blocked"):
        web_tools.validate_public_url("https://example.org/document")


@pytest.mark.parametrize("url", ["file:///C:/secrets.txt", "ftp://example.org/file", "https://user:password@example.org", "https://example.org:8080/"])
def test_web_reader_rejects_nonhttp_credentials_and_nonstandard_ports(url):
    with pytest.raises(ValueError):
        web_tools.validate_public_url(url)


def test_web_reader_allows_public_https_without_network(monkeypatch):
    monkeypatch.setattr(web_tools.socket, "getaddrinfo", lambda *a, **k: address("93.184.216.34"))
    assert web_tools.validate_public_url("https://example.org/document") == "https://example.org/document"


def test_mixed_public_private_dns_is_rejected(monkeypatch):
    monkeypatch.setattr(web_tools.socket, "getaddrinfo", lambda *a, **k: address("93.184.216.34") + address("127.0.0.1"))
    with pytest.raises(ValueError, match="blocked"):
        web_tools.validate_public_url("https://example.org/document")


def test_public_page_redirect_to_private_network_is_not_followed(monkeypatch):
    requests = []
    monkeypatch.setattr(web_tools.socket, "getaddrinfo", lambda host, *a, **k:
        address("93.184.216.34") if host == "example.org" else address("127.0.0.1"))

    class RedirectResponse:
        is_redirect = True
        headers = {"location": "http://localhost/private"}

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    class FakeHTTP:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def stream(self, method, target):
            requests.append(target)
            return RedirectResponse()

    monkeypatch.setattr(web_tools.httpx, "Client", FakeHTTP)
    with pytest.raises(ValueError, match="blocked"):
        web_tools.read_webpage("https://example.org/start")
    assert requests == ["https://example.org/start"]


def test_run_storage_round_trip(corpus):
    store, _ = corpus
    request = {"question": "A test research question", "collection_id": "a", "mode": "verified"}
    run_id = store.create_run(request)
    assert store.get_run(run_id)["status"] == "queued"
    store.save_run(run_id, "completed", {"answer": "alpha"})
    assert store.get_run(run_id)["result"]["answer"] == "alpha"
