from __future__ import annotations

import asyncio
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
executor = None
active = {}
active_lock = threading.RLock()

@asynccontextmanager
async def lifespan(app):
    global executor
    store.recover_interrupted()
    with active_lock:
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="research")
    try:
        yield
    finally:
        with active_lock:
            pool, executor = executor, None
            for rid, context in list(active.items()):
                context["cancel"].set()
                if context["future"].cancel():
                    store.save_run(rid, "cancelled")
        # Let an in-flight request observe cancellation and persist its outcome
        # before a new lifespan can recover or overwrite its database records.
        await asyncio.to_thread(pool.shutdown, wait=True, cancel_futures=True)

app = FastAPI(title="Khoj Research Lab", version="1.0.0", lifespan=lifespan)


def origin_tuple(value):
    parsed = urlparse(value)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.path or parsed.params or parsed.query or parsed.fragment):
        raise ValueError("Invalid origin")
    port = parsed.port if parsed.port is not None else (443 if parsed.scheme == "https" else 80)
    return parsed.scheme, parsed.hostname, port

@app.middleware("http")
async def local_only(request: Request, call_next):
    try:
        local_host = request.url.hostname in ("127.0.0.1", "localhost", "::1", "testserver")
    except ValueError:
        local_host = False
    if not local_host:
        return JSONResponse({"detail": "This service is local-only"}, status_code=403)
    origin = request.headers.get("origin")
    if origin and request.method not in ("GET", "HEAD"):
        try:
            same_origin = origin_tuple(origin) == origin_tuple(f"{request.url.scheme}://{request.url.netloc}")
        except ValueError:
            same_origin = False
        if not same_origin:
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
    return {"model": config.MODEL, "configured": config.model_configured(),
            "thinking": config.thinking_policy(),
            "structured_output": config.STRUCTURED_OUTPUT,
            "embedding_model": config.EMBEDDING_MODEL, "limits": config.LIMITS,
            "retrieval": retriever.settings.describe(),
            "agent_policy": config.AGENT_POLICY,
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
    results, errors = [], []
    for file in files:
        try:
            content = await file.read(10_000_001)
            if len(content) > 10_000_000:
                raise ValueError("Each file must be at most 10 MB")
            document = await asyncio.to_thread(decode_upload, file.filename or "untitled.txt", content)
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
    agent = None
    try:
        if context["cancel"].is_set():
            store.save_run(rid, "cancelled")
            return
        store.save_run(rid, "running")
        agent = ResearchAgent(body, retriever, progress=context["progress"].append, cancel=context["cancel"])
        result = agent.run()
        store.save_run(rid, "cancelled" if context["cancel"].is_set() else "completed", result=result)
    except Exception as error:
        partial = {"question": body.question, "mode": body.mode, "answer": "", "report": "Run did not complete. Inspect the failure trace; this is not a verified report.",
            "claims": [], "evidence": list(agent.evidence.values()) if agent else [], "trace": agent.trace if agent else [],
            "usage": agent.client.usage_summary() if agent else {}, "model_calls": agent.client.events if agent else [],
            "stop_reason": agent.stop_reason if agent and agent.stop_reason != "completed" else "error",
            "unresolved": [redact(error)]}
        store.save_run(rid, "cancelled" if context["cancel"].is_set() else "failed", result=partial, error=redact(error))


def release_run(rid, context):
    with active_lock:
        if active.get(rid) is context:
            del active[rid]

@app.post("/api/research", status_code=202)
def research(body: ResearchRequest):
    if not config.model_configured():
        raise HTTPException(503, "Configure LLM_API_KEY in the local .env file")
    if body.mode != "no_tools" and not store.collection_exists(body.collection_id):
        raise HTTPException(404, "Collection not found")
    with active_lock:
        if executor is None:
            raise HTTPException(503, "Research worker is not running")
        inflight = [k for k,v in active.items() if not v.get("future") or not v["future"].done()]
        if len(inflight) >= 10:
            raise HTTPException(429, "Research queue is full (10 runs)")
        rid = store.create_run(body.model_dump())
        context = {"cancel": threading.Event(), "progress": []}
        active[rid] = context
        try:
            context["future"] = executor.submit(process_run, rid, body, context)
        except RuntimeError:
            del active[rid]
            store.save_run(rid, "failed", error="Research worker is unavailable")
            raise HTTPException(503, "Research worker is unavailable") from None
    # May run synchronously for an already-finished future; register only after
    # the context has its future and remove completed/cancelled traces from RAM.
    context["future"].add_done_callback(lambda _: release_run(rid, context))
    return {"id": rid, "status": "queued"}

@app.get("/api/runs")
def runs():
    return {"runs": store.list_runs()}

@app.get("/api/runs/{rid}")
def get_run(rid: str):
    item = store.get_run(rid)
    if item is None:
        raise HTTPException(404, "Run not found")
    with active_lock:
        item["progress"] = list(active.get(rid, {}).get("progress", []))
    return item

@app.post("/api/runs/{rid}/cancel")
def cancel_run(rid: str):
    item = store.get_run(rid)
    if item is None:
        raise HTTPException(404, "Run not found")
    with active_lock:
        context = active.get(rid)
        if context and item["status"] in ("queued", "running"):
            context["cancel"].set()
            if context["future"].cancel():
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
