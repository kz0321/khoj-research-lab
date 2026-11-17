"""Download a pinned optional local inference runtime; does not modify app .env.

Usage: python scripts/setup_local_model.py [--backend cpu|vulkan|both]
Downloads approximately 1.2 GB to this project, verifies published SHA-256s,
and preserves model/runtime licensing and source provenance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime" / "local-model"
MODEL_DIR = ROOT / "models" / "generative"
TAG = "b12428"
LLAMA_COMMIT = "b4c0e00a4fcc0287d0bb32fd7cb0d8b286af73ed"
MODEL_REPO = "Qwen/Qwen2.5-1.5B-Instruct-GGUF"
MODEL_REVISION = "91cad51170dc346986eccefdc2dd33a9da36ead9"
MODEL_FILE = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
MODEL_SHA256 = "6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"
MODEL_SIZE = 1_117_320_736
BUILDS = {
    "cpu": {"name": "llama-b12428-bin-win-cpu-x64.zip", "size": 25_212_756,
            "sha256": "4ebc7fb961cf707e3b61396806e62c9e4065e42990cfc31f238eb48264a465b2"},
    "vulkan": {"name": "llama-b12428-bin-win-vulkan-x64.zip", "size": 38_289_478,
               "sha256": "598b0672b20784752a6fbea3b73523f0905f094326b13b0d734ee47e94e6b986"},
}
HEADERS = {"User-Agent": "Khoj-Research-Lab-Local-Setup/1.0"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path, expected_hash: str | None = None,
             expected_size: int | None = None) -> dict:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and (expected_size is None or destination.stat().st_size == expected_size):
        digest = sha256(destination)
        if expected_hash is None or digest == expected_hash:
            print(f"Verified existing {destination.name}", flush=True)
            return {"path": str(destination.relative_to(ROOT)).replace("\\", "/"),
                    "url": url, "sha256": digest, "size_bytes": destination.stat().st_size}
    partial = destination.with_name(destination.name + ".part")
    for attempt in range(3):
        try:
            offset = partial.stat().st_size if partial.exists() else 0
            if expected_size is not None and offset == expected_size and sha256(partial) == expected_hash:
                partial.replace(destination)
                break
            headers = dict(HEADERS)
            if offset:
                headers["Range"] = f"bytes={offset}-"
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=60) as response:
                resumed = response.status == 206 and response.headers.get("Content-Range", "").startswith(f"bytes {offset}-")
                if not resumed:
                    offset = 0
                mode = "ab" if resumed else "wb"
                total = offset + int(response.headers.get("Content-Length", 0))
                start = time.monotonic()
                last_print = start
                received = offset
                with partial.open(mode) as stream:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        stream.write(chunk)
                        received += len(chunk)
                        now = time.monotonic()
                        if now - last_print >= 12:
                            speed = (received - offset) / max(now - start, 0.01) / 1e6
                            print(f"{destination.name}: {received / 1e6:.0f}/{total / 1e6:.0f} MB ({speed:.1f} MB/s)", flush=True)
                            last_print = now
            if expected_size is not None and partial.stat().st_size != expected_size:
                raise ValueError(f"Size mismatch for {destination.name}")
            if expected_hash and sha256(partial) != expected_hash:
                # Only the explicit, task-owned incomplete download is discarded.
                partial.unlink()
                raise ValueError(f"SHA-256 mismatch for {destination.name}")
            partial.replace(destination)
            break
        except (OSError, ValueError, urllib.error.URLError) as error:
            if attempt == 2:
                raise
            print(f"Download attempt {attempt + 1} failed ({type(error).__name__}); resuming.", flush=True)
            time.sleep(2)
    digest = sha256(destination)
    print(f"Verified {destination.name}: {digest}", flush=True)
    return {"path": str(destination.relative_to(ROOT)).replace("\\", "/"),
            "url": url, "sha256": digest, "size_bytes": destination.stat().st_size}


def unpack(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    digest = sha256(archive)
    marker = destination / ".archive-sha256"
    if marker.exists() and marker.read_text(encoding="ascii").strip() == digest and list(destination.rglob("llama-server.exe")):
        return
    root = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            path = (root / member.filename).resolve()
            if not path.is_relative_to(root):
                raise ValueError("Unsafe archive member path")
        bundle.extractall(destination)
    if not list(destination.rglob("llama-server.exe")):
        raise RuntimeError("The archive did not contain llama-server.exe")
    marker.write_text(digest + "\n", encoding="ascii")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["cpu", "vulkan", "both"], default="both")
    args = parser.parse_args()
    free = shutil.disk_usage(ROOT).free
    if free < 2_500_000_000 and not (MODEL_DIR / MODEL_FILE).exists():
        raise SystemExit("At least 2.5 GB of free disk space is required.")
    RUNTIME.mkdir(parents=True, exist_ok=True)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    artifacts = []
    backends = list(BUILDS) if args.backend == "both" else [args.backend]
    for backend in backends:
        info = BUILDS[backend]
        url = f"https://github.com/ggml-org/llama.cpp/releases/download/{TAG}/{info['name']}"
        archive = RUNTIME / "downloads" / info["name"]
        artifacts.append({"kind": "llama.cpp", "backend": backend,
                          **download(url, archive, info["sha256"], info["size"])})
        unpack(archive, RUNTIME / "llama" / backend)
    artifacts.append({"kind": "model", **download(
        f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/{MODEL_FILE}",
        MODEL_DIR / MODEL_FILE, MODEL_SHA256, MODEL_SIZE)})
    artifacts.append({"kind": "llama-license", **download(
        f"https://raw.githubusercontent.com/ggml-org/llama.cpp/{LLAMA_COMMIT}/LICENSE",
        RUNTIME / "LLAMA-LICENSE.txt")})
    artifacts.append({"kind": "model-license", **download(
        f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/LICENSE",
        MODEL_DIR / "QWEN-LICENSE.txt")})
    artifacts.append({"kind": "model-card", **download(
        f"https://huggingface.co/{MODEL_REPO}/resolve/{MODEL_REVISION}/README.md",
        MODEL_DIR / "QWEN-MODEL-CARD.md")})
    manifest = {"prepared_at_utc": datetime.now(timezone.utc).isoformat(),
                "llama_cpp": {"release": TAG, "commit": LLAMA_COMMIT, "license": "MIT"},
                "model": {"repository": MODEL_REPO, "revision": MODEL_REVISION, "quantization": "Q4_K_M",
                          "alias": "qwen2.5-1.5b-instruct", "license": "Apache-2.0"},
                "artifacts": artifacts,
                "configuration_note": "Optional local fallback only; app .env was not changed."}
    previous_manifest = RUNTIME / "source-manifest.json"
    if previous_manifest.exists():
        try:
            previous_probe = json.loads(previous_manifest.read_text(encoding="utf-8")).get("runtime_probe")
            if previous_probe:
                probe = ROOT / previous_probe["path"]
                if probe.is_file() and sha256(probe) == previous_probe["sha256"]:
                    manifest["runtime_probe"] = previous_probe
        except (OSError, ValueError, KeyError):
            pass
    (RUNTIME / "source-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("Local fallback prepared. Start using scripts/start_local_model.ps1.", flush=True)


if __name__ == "__main__":
    main()
