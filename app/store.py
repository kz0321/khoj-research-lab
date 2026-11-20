from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from .config import RUNTIME

def now():
    return datetime.now(timezone.utc).isoformat()

def document_digest(document):
    return hashlib.sha256(json.dumps({"text": document["text"], "sentences": document.get("sentences"),
        "pages": document.get("metadata", {}).get("pages")}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

class Store:
    def __init__(self, path: Path | str = RUNTIME / "research.sqlite3"):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS collections(id TEXT PRIMARY KEY,name TEXT,created_at TEXT);
            CREATE TABLE IF NOT EXISTS documents(id TEXT,collection_id TEXT,title TEXT,text TEXT,
                url TEXT,metadata TEXT,sha256 TEXT,PRIMARY KEY(collection_id,id));
            CREATE TABLE IF NOT EXISTS chunks(id TEXT PRIMARY KEY,collection_id TEXT,source_id TEXT,
                title TEXT,text TEXT,location TEXT,url TEXT,vector BLOB);
            CREATE INDEX IF NOT EXISTS chunks_collection ON chunks(collection_id);
            CREATE INDEX IF NOT EXISTS chunks_source ON chunks(collection_id,source_id);
            CREATE INDEX IF NOT EXISTS chunks_title ON chunks(collection_id,title);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,question TEXT,collection_id TEXT,
                mode TEXT,status TEXT,created_at TEXT,request TEXT,result TEXT,error TEXT);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            # sqlite3's context manager commits/rolls back but does not close.
            with db:
                yield db
        finally:
            db.close()

    def collections(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("""SELECT c.*,
                (SELECT count(*) FROM documents d WHERE d.collection_id=c.id) AS documents,
                (SELECT count(*) FROM chunks k WHERE k.collection_id=c.id) AS chunks
                FROM collections c ORDER BY c.created_at DESC""")]

    def collection_exists(self, cid):
        with self.connect() as db:
            return db.execute("SELECT 1 FROM collections WHERE id=?", (cid,)).fetchone() is not None

    def create_collection(self, name, cid=None):
        cid = cid or uuid.uuid4().hex[:12]
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO collections VALUES(?,?,?)", (cid, name, now()))
        return cid

    def save_document(self, cid, document, chunks, vectors):
        vectors = np.asarray(vectors, dtype=np.float32)
        if chunks and (vectors.ndim != 2 or vectors.shape[0] != len(chunks)
                       or vectors.shape[1] == 0 or not np.isfinite(vectors).all()):
            raise ValueError("Embedding vectors must be finite and match every passage")
        if not chunks and vectors.size:
            raise ValueError("Embedding vectors supplied without passages")
        did = document.get("id") or hashlib.sha256(document["title"].encode()).hexdigest()[:20]
        digest = document_digest(document)
        with self.connect() as db:
            # Serialize the dimension check with the replacement, including
            # concurrent imports through another Retriever instance.
            db.execute("BEGIN IMMEDIATE")
            if chunks:
                previous = db.execute("SELECT length(vector) FROM chunks WHERE collection_id=? LIMIT 1", (cid,)).fetchone()
                if previous and previous[0] != vectors.shape[1] * 4:
                    raise ValueError("Embedding dimensions differ from this collection; rebuild it in a new collection")
            db.execute("DELETE FROM chunks WHERE collection_id=? AND source_id=?", (cid, did))
            db.execute("INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?,?,?)",
                (did, cid, document["title"], document["text"], document.get("url"),
                 json.dumps(document.get("metadata", {}), ensure_ascii=False), digest))
            for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
                key = hashlib.sha256(f'{cid}:{did}:{digest}:{i}'.encode()).hexdigest()[:24]
                db.execute("INSERT INTO chunks VALUES(?,?,?,?,?,?,?,?)",
                    (key, cid, did, document["title"], chunk["text"],
                     json.dumps(chunk["location"], ensure_ascii=False), document.get("url"), vector.tobytes()))
        return {"id": did, "title": document["title"], "chunks": len(chunks), "sha256": digest}

    def existing_document(self, cid, document):
        did = document.get("id") or hashlib.sha256(document["title"].encode()).hexdigest()[:20]
        with self.connect() as db:
            row = db.execute("SELECT * FROM documents WHERE collection_id=? AND id=?", (cid,did)).fetchone()
            if row and row["sha256"] == document_digest(document) and row["title"] == document["title"] and row["url"] == document.get("url"):
                count = db.execute("SELECT count(*) FROM chunks WHERE collection_id=? AND source_id=?", (cid,did)).fetchone()[0]
                return {"id":did,"title":document["title"],"chunks":count,"sha256":row["sha256"],"cached":True}
        return None

    def chunks(self, cid):
        with self.connect() as db:
            rows = [dict(r) for r in db.execute("SELECT * FROM chunks WHERE collection_id=? ORDER BY id", (cid,))]
        for row in rows:
            row["location"] = json.loads(row["location"])
        return rows

    def document_chunks(self, cid, source_id, *, match_title=False):
        # File reading needs only the requested source, never its embeddings.
        fields = "id,collection_id,source_id,title,text,location,url"
        query = f"SELECT {fields} FROM chunks WHERE collection_id=? AND source_id=?"
        params = (cid, source_id)
        if match_title:
            # Separate indexed branches: an OR can make SQLite scan every
            # chunk in the collection. UNION also removes ID/title overlaps.
            query += f" UNION SELECT {fields} FROM chunks WHERE collection_id=? AND title=?"
            params += (cid, source_id)
        with self.connect() as db:
            rows = [dict(r) for r in db.execute(query + " ORDER BY id", params)]
        for row in rows:
            row["location"] = json.loads(row["location"])
        return rows

    def create_run(self, request):
        rid = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?)", (rid, request["question"],
                request["collection_id"], request["mode"], "queued", now(), json.dumps(request), None, None))
        return rid

    def save_run(self, rid, status, result=None, error=None):
        with self.connect() as db:
            db.execute("UPDATE runs SET status=?,result=?,error=? WHERE id=?",
                (status, json.dumps(result, ensure_ascii=False) if result else None, error, rid))

    def get_run(self, rid):
        with self.connect() as db:
            row = db.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
        if row is None:
            return None
        item = dict(row)
        for k in ("request", "result"):
            item[k] = json.loads(item[k]) if item[k] else None
        return item

    def list_runs(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT id,question,mode,status,created_at FROM runs ORDER BY created_at DESC LIMIT 100")]

    def recover_interrupted(self):
        with self.connect() as db:
            db.execute("UPDATE runs SET status='failed',error='Server restarted before this run completed.' WHERE status IN ('running','queued')")
