"""Real ASGI routes with temporary storage; no model or public-network calls."""
import asyncio
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config, main
from app.store import Store


@pytest.fixture
def isolated_app(tmp_path, monkeypatch):
    store = Store(tmp_path / "api.sqlite3")
    store.create_collection("Test", "a")
    monkeypatch.setattr(main, "store", store)
    monkeypatch.setattr(config, "API_KEY", "test-key-never-sent")
    return main.app


def wait_for_terminal(client, rid):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        run = client.get(f"/api/runs/{rid}").json()
        if run["status"] not in ("queued", "running"):
            return run
        time.sleep(.01)
    pytest.fail("Run did not reach a terminal state")


@pytest.mark.parametrize("origin", ["null", "http://[", "http://127.0.0.1:bad",
    "https://127.0.0.1", "http://localhost", "http://127.0.0.1:9999", "http://example.com"])
def test_invalid_or_cross_origin_mutation_is_rejected(isolated_app, origin):
    with TestClient(isolated_app, base_url="http://127.0.0.1", raise_server_exceptions=False) as client:
        response = client.post("/api/collections", json={"name": "Blocked"}, headers={"Origin": origin})
        assert response.status_code == 403
        assert len(client.get("/api/collections").json()["collections"]) == 1


def test_same_origin_default_port_and_direct_clients_work(isolated_app):
    with TestClient(isolated_app, base_url="http://127.0.0.1") as client:
        for headers in ({}, {"Origin": "http://127.0.0.1:80"}):
            assert client.post("/api/collections", json={"name": "Allowed"}, headers=headers).status_code == 200


@pytest.mark.parametrize("key", ["", "   ", "replace-with-your-own-api-key"])
def test_missing_or_example_credentials_do_not_queue_runs(isolated_app, monkeypatch, key):
    monkeypatch.setattr(config, "API_KEY", key)
    with TestClient(isolated_app) as client:
        assert client.get("/api/status").json()["configured"] is False
        assert client.post("/api/research", json={"question": "Test question", "mode": "no_tools"}).status_code == 503
        assert client.get("/api/runs").json()["runs"] == []


def test_agent_initialization_failure_is_persisted_and_redacted(isolated_app, monkeypatch):
    def broken_agent(*args, **kwargs):
        raise RuntimeError("Initialization failed: " + config.API_KEY)
    monkeypatch.setattr(main, "ResearchAgent", broken_agent)
    with TestClient(isolated_app) as client:
        response = client.post("/api/research", json={"question": "Test question", "mode": "no_tools"})
        assert response.status_code == 202
        run = wait_for_terminal(client, response.json()["id"])
        assert run["status"] == "failed"
        assert "Initialization failed" in run["error"]
        assert config.API_KEY not in str(run)


def test_lifespan_restart_accepts_work_and_releases_completed_runs(isolated_app, monkeypatch):
    class Agent:
        def __init__(self, *args, **kwargs):
            pass
        def run(self):
            return {"answer": "A result", "report": "A result"}
    monkeypatch.setattr(main, "ResearchAgent", Agent)
    for _ in range(2):
        with TestClient(isolated_app) as client:
            response = client.post("/api/research", json={"question": "Test question", "mode": "no_tools"})
            assert response.status_code == 202
            assert wait_for_terminal(client, response.json()["id"])["status"] == "completed"
        assert not main.active


def test_upload_parsing_does_not_block_health_requests(isolated_app, monkeypatch):
    started, release = threading.Event(), threading.Event()
    def slow_parse(filename, content):
        started.set()
        if not release.wait(2):
            raise TimeoutError("Parsing blocked the event loop")
        return {"title": filename, "text": "A fact"}
    monkeypatch.setattr(main, "decode_upload", slow_parse)
    monkeypatch.setattr(main.retriever, "ingest", lambda *args: {"id": "d", "chunks": 1})

    async def scenario():
        async with isolated_app.router.lifespan_context(isolated_app):
            transport = httpx.ASGITransport(app=isolated_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://127.0.0.1") as client:
                upload = asyncio.create_task(client.post("/api/collections/a/documents",
                    files={"files": ("test.txt", b"A fact", "text/plain")}))
                try:
                    assert await asyncio.to_thread(started.wait, 2)
                    assert not release.is_set()
                    assert (await asyncio.wait_for(client.get("/api/health"), .8)).status_code == 200
                finally:
                    release.set()
                assert (await upload).status_code == 200
    asyncio.run(scenario())


def test_queue_capacity_and_cancelling_queued_work(isolated_app, monkeypatch):
    started, release = threading.Event(), threading.Event()
    processed = []
    class Agent:
        def __init__(self, request, *args, **kwargs):
            self.question = request.question
        def run(self):
            started.set()
            assert release.wait(3)
            processed.append(self.question)
            return {"answer": "A result", "report": "A result"}
    monkeypatch.setattr(main, "ResearchAgent", Agent)
    with TestClient(isolated_app) as client:
        def submit(question):
            return client.post("/api/research", json={"question": question, "mode": "no_tools"})
        try:
            first = submit("First request").json()["id"]
            assert started.wait(1)
            queued = [submit(f"Queued request {i}").json()["id"] for i in range(9)]
            assert submit("Overflow request").status_code == 429
            assert client.post(f"/api/runs/{queued[0]}/cancel").status_code == 200
            assert client.get(f"/api/runs/{queued[0]}").json()["status"] == "cancelled"
            replacement = submit("Replacement request")
            assert replacement.status_code == 202
        finally:
            release.set()
        for rid in [first, *queued[1:], replacement.json()["id"]]:
            assert wait_for_terminal(client, rid)["status"] == "completed"
    assert "Queued request 0" not in processed
    assert len(processed) == 10
    assert not main.active


def test_shutdown_cancels_running_and_queued_work(isolated_app, monkeypatch):
    started = threading.Event()
    class Agent:
        def __init__(self, request, retriever, *, cancel, **kwargs):
            self.cancel = cancel
        def run(self):
            started.set()
            assert self.cancel.wait(3)
            return {"answer": "Late answer", "report": "Late answer"}
    monkeypatch.setattr(main, "ResearchAgent", Agent)
    with TestClient(isolated_app) as client:
        ids = []
        ids.append(client.post("/api/research", json={"question": "First request", "mode": "no_tools"}).json()["id"])
        assert started.wait(1)
        ids.append(client.post("/api/research", json={"question": "Queued request", "mode": "no_tools"}).json()["id"])
    assert all(main.store.get_run(rid)["status"] == "cancelled" for rid in ids)
    assert not main.active


def test_worker_submission_failure_is_explicit_and_does_not_leak_queue_slot(isolated_app, monkeypatch):
    with TestClient(isolated_app) as client:
        def failed_submit(*args):
            raise RuntimeError("Executor unavailable")
        monkeypatch.setattr(main.executor, "submit", failed_submit)
        response = client.post("/api/research", json={"question": "Test question", "mode": "no_tools"})
        assert response.status_code == 503
        assert main.store.list_runs()[0]["status"] == "failed"
        assert not main.active


def test_upload_reports_partial_success_and_rejects_oversized_batch(isolated_app, monkeypatch):
    monkeypatch.setattr(main.retriever, "ingest", lambda *args: {"id": "d", "chunks": 1})
    with TestClient(isolated_app) as client:
        response = client.post("/api/collections/a/documents", files=[
            ("files", ("ok.txt", b"A fact")), ("files", ("bad.exe", b"binary"))])
        assert response.status_code == 200
        assert len(response.json()["imported"]) == len(response.json()["errors"]) == 1
        response = client.post("/api/collections/a/documents",
            files=[("files", (f"file-{i}.txt", b"A fact")) for i in range(21)])
        assert response.status_code == 422
