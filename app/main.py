from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from . import config
from .agent import ResearchAgent
from .khoj_core import UPSTREAM_COMMIT
from .llm import redact
from .retrieval import Retriever, decode_upload
from .schemas import CollectionInput, ImportRequest, ResearchRequest
from .store import Store

store = Store()
retriever = Retriever(store)
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="research")
active = {}
active_lock = threading.Lock()

@asynccontextmanager
async def lifespan(app):
    store.recover_interrupted()
    yield
    for run in list(active.values()):
        run["cancel"].set()
    executor.shutdown(wait=False, cancel_futures=True)

app = FastAPI(title="Khoj Research Lab", version="1.0.0", lifespan=lifespan)

@app.middleware("http")
async def local_only(request: Request, call_next):
    if request.url.hostname not in ("127.0.0.1", "localhost", "::1", "testserver"):
        return JSONResponse({"detail": "This service is local-only"}, status_code=403)
    origin = request.headers.get("origin")
    if origin and request.method not in ("GET", "HEAD"):
        parsed = urlparse(origin)
        if parsed.hostname not in ("127.0.0.1", "localhost", "::1") or parsed.port != request.url.port:
            return JSONResponse({"detail": "Cross-origin mutations are blocked"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'"
    return response

@app.get("/")
def index():
    return FileResponse(config.ROOT / "app/static/index.html")

@app.get("/api/health")
def health():
    return {"ok": True, "service": "Khoj Research Lab"}

@app.get("/api/status")
def status():
    return {"model": config.MODEL, "configured": bool(config.API_KEY),
            "thinking": "disabled for official DeepSeek API", "structured_output": config.STRUCTURED_OUTPUT,
            "embedding_model": config.EMBEDDING_MODEL, "limits": config.LIMITS,
            "retrieval": retriever.settings.describe(),
            "upstream_commit": UPSTREAM_COMMIT, "binding": "127.0.0.1",
            "implementation": "Khoj-derived Windows course runtime (not the full upstream server)"}

@app.get("/api/collections")
def collections():
    return {"collections": store.collections()}

@app.post("/api/collections")
def create_collection(body: CollectionInput):
    return {"id": store.create_collection(body.name, body.id)}

@app.post("/api/collections/{cid}/import")
def import_documents(cid: str, body: ImportRequest):
    if not store.collection_exists(cid):
        raise HTTPException(404, "Collection not found")
    results, errors = [], []
    for doc in body.documents:
        try:
            results.append(retriever.ingest(cid, doc.model_dump()))
        except Exception as e:
            errors.append({"title": doc.title, "error": redact(e)})
    if not results:
        raise HTTPException(422, errors)
    return {"imported": results, "errors": errors}

@app.post("/api/collections/{cid}/documents")
async def upload_documents(cid: str, files: list[UploadFile] = File(...)):
    if not store.collection_exists(cid):
        raise HTTPException(404, "Collection not found")
    if len(files) > 20:
        raise HTTPException(422, "Upload at most 20 files per batch")
    # Offload parsing and CPU embeddings so progress polling remains responsive.
    import asyncio
    results, errors = [], []
    for file in files:
        content = await file.read(10_000_001)
        try:
            if len(content) > 10_000_000:
                raise ValueError("Each file must be at most 10 MB")
            document = decode_upload(file.filename or "untitled.txt", content)
            results.append(await asyncio.to_thread(retriever.ingest, cid, document))
        except Exception as e:
            errors.append({"title": file.filename, "error": redact(e)})
        finally:
            await file.close()
    if not results:
        raise HTTPException(422, errors)
    return {"imported": results, "errors": errors}

@app.post("/api/demo")
def demo():
    cid = store.create_collection("Demo · Retrieval methods & experimental comparability", "demo")
    if not any(c["id"] == cid and c["documents"] >= 5 for c in store.collections()):
        for path in sorted((config.ROOT / "data/demo").glob("*.md")):
            retriever.ingest(cid, {"id": path.stem, "title": path.name, "text": path.read_text(encoding="utf-8"),
                                  "metadata": {"synthetic_demo": True, "license": "CC0-1.0"}})
    return {"collection_id": cid}

def process_run(rid, body, context):
    if context["cancel"].is_set():
        store.save_run(rid, "cancelled")
        return
    store.save_run(rid, "running")
    agent = ResearchAgent(body, retriever, progress=context["progress"].append, cancel=context["cancel"])
    try:
        result = agent.run()
        store.save_run(rid, "cancelled" if context["cancel"].is_set() else "completed", result=result)
    except Exception as error:
        partial = {"question": body.question, "mode": body.mode, "answer": "", "report": "Run did not complete. Inspect the failure trace; this is not a verified report.",
            "claims": [], "evidence": list(agent.evidence.values()), "trace": agent.trace,
            "usage": agent.client.usage_summary(), "model_calls": agent.client.events,
            "stop_reason": agent.stop_reason if agent.stop_reason != "completed" else "error",
            "unresolved": [redact(error)]}
        store.save_run(rid, "cancelled" if context["cancel"].is_set() else "failed", result=partial, error=redact(error))

@app.post("/api/research", status_code=202)
def research(body: ResearchRequest):
    if not config.API_KEY:
        raise HTTPException(503, "Configure LLM_API_KEY in the local .env file")
    if body.mode != "no_tools" and not store.collection_exists(body.collection_id):
        raise HTTPException(404, "Collection not found")
    with active_lock:
        inflight = [k for k,v in active.items() if not v.get("future") or not v["future"].done()]
        if len(inflight) >= 10:
            raise HTTPException(429, "Research queue is full (10 runs)")
        rid = store.create_run(body.model_dump())
        context = {"cancel": threading.Event(), "progress": []}
        active[rid] = context
        context["future"] = executor.submit(process_run, rid, body, context)
    return {"id": rid, "status": "queued"}

@app.get("/api/runs")
def runs():
    return {"runs": store.list_runs()}

@app.get("/api/runs/{rid}")
def get_run(rid: str):
    item = store.get_run(rid)
    if item is None:
        raise HTTPException(404, "Run not found")
    item["progress"] = list(active.get(rid, {}).get("progress", []))
    return item

@app.post("/api/runs/{rid}/cancel")
def cancel_run(rid: str):
    item = store.get_run(rid)
    if item is None:
        raise HTTPException(404, "Run not found")
    if rid in active and item["status"] in ("queued", "running"):
        active[rid]["cancel"].set()
        if active[rid]["future"].cancel():
            store.save_run(rid, "cancelled")
    return {"id": rid, "cancellation_requested": True,
            "note": "An in-flight model request may finish before cancellation is observed."}

@app.get("/api/runs/{rid}/export")
def export_run(rid: str, format: str = "json"):
    item = store.get_run(rid)
    if item is None or not item["result"]:
        raise HTTPException(404, "No result available")
    if format not in ("json", "md"):
        raise HTTPException(422, "Use json or md")
    payload = json.dumps(item, ensure_ascii=False, indent=2) if format == "json" else item["result"]["report"]
    return Response(payload, media_type="application/json" if format == "json" else "text/markdown",
                    headers={"Content-Disposition": f'attachment; filename="research-{rid[:8]}.{format}"'})

app.mount("/static", StaticFiles(directory=str(config.ROOT / "app/static"), check_dir=False), name="static")
