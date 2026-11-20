"""Storage regressions: resource lifetime, atomic writes and scoped reads."""
import sqlite3

import numpy as np
import pytest

from app.store import Store
from app.retrieval import Retriever


def test_connection_closes_after_commit_and_rollback(tmp_path):
    store = Store(tmp_path / "store.sqlite3")
    with store.connect() as db:
        db.execute("INSERT INTO collections VALUES ('kept', 'Kept', 'today')")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        db.execute("SELECT 1")
    assert store.collection_exists("kept")

    with pytest.raises(RuntimeError, match="rollback"):
        with store.connect() as failed:
            failed.execute("INSERT INTO collections VALUES ('lost', 'Lost', 'today')")
            raise RuntimeError("rollback")
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        failed.execute("SELECT 1")
    assert not store.collection_exists("lost")


@pytest.mark.parametrize("vectors", [[], [[1, 0], [0, 1]], [[float('nan'), 0]], [[1, 2, 3]]])
def test_invalid_embedding_cannot_replace_existing_document(tmp_path, vectors):
    store = Store(tmp_path / "store.sqlite3")
    store.create_collection("Test", "a")
    original = {"id": "d", "title": "Original", "text": "Original fact."}
    chunk = {"text": original["text"], "location": {"start_line": 1}}
    store.save_document("a", original, [chunk], np.array([[1, 0]], dtype=np.float32))
    changed = {**original, "text": "Replacement fact."}
    with pytest.raises(ValueError, match="[Vv]ector|[Ee]mbedding"):
        store.save_document("a", changed, [{**chunk, "text": changed["text"]}], np.array(vectors))
    assert store.existing_document("a", original)
    assert store.chunks("a")[0]["text"] == original["text"]


def test_document_read_is_scoped_and_keeps_fragment_order(tmp_path, monkeypatch):
    store = Store(tmp_path / "store.sqlite3")
    store.create_collection("Test", "a")
    store.create_collection("Private", "b")
    chunks = [{"text": f"Fragment {i}", "location": {"start_line": 1, "end_line": 1,
               "section_start_char": i * 1000}} for i in range(12)]
    vectors = np.ones((12, 2), dtype=np.float32)
    for cid in ("a", "b"):
        store.save_document(cid, {"id": "d", "title": "Paper", "text": "body"}, chunks, vectors)
    store.save_document("a", {"id": "other", "title": "Other", "text": "unrelated"},
                        [{"text": "unrelated", "location": {}}], np.ones((1, 2), dtype=np.float32))

    def forbid_full_scan(*args):
        pytest.fail("Reading one document must not load the entire collection")
    monkeypatch.setattr(store, "chunks", forbid_full_scan)
    retriever = Retriever(store)
    for path in ("d", "Paper"):
        rows = retriever.read_file("a", path)
        assert [r["text"] for r in rows] == [f"Fragment {i}" for i in range(8)]
        assert all(r["collection_id"] == "a" and "vector" not in r for r in rows)
    assert retriever.read_file("a", "missing") == []
