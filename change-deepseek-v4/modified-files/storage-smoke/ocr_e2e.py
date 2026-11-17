"""Real OCR end-to-end smoke test.

Starts the API, the backend worker, and one OCR worker with plain Python
subprocess calls, then verifies:

    upload image -> parse -> OCR worker -> chunks in index -> search hit

All paths and settings are explicit; nothing is downloaded and no shell
string is built dynamically.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

import httpx
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
MAIN_PY = ROOT / ".venv-main" / "Scripts" / "python.exe"
OCR_PY = ROOT / "env_check" / ".venv-ocr" / "Scripts" / "python.exe"
BACKEND_DIR = ROOT / "backend"
OCR_DIR = ROOT / "services" / "ocr_worker"

DATABASE_URL = "postgresql://docmgr:change-me@127.0.0.1:55432/docmgr_test"
OPENSEARCH_URL = "http://127.0.0.1:9200"
API_PORT = 8011
API_URL = f"http://127.0.0.1:{API_PORT}"

RUN_ID = time.strftime("%Y%m%d-%H%M%S")
INDEX_PREFIX = f"smokeocr{RUN_ID.replace('-', '')}"
RUN_DIR = ROOT / "storage-smoke" / "ocr-e2e" / RUN_ID

T = TypeVar("T")


def say(message: str) -> None:
    print(message, flush=True)


def wait_for(what: str, probe: Callable[[], T | None], timeout: float) -> T:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = probe()
            if value is not None:
                return value
        except Exception as exc:  # keep polling until the deadline
            last_error = exc
        time.sleep(0.5)
    suffix = f"; last error: {last_error}" if last_error else ""
    raise TimeoutError(f"timed out waiting for {what}{suffix}")


def log_tail(path: Path, lines: int = 40) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "(log not available)"
    return "\n".join(content[-lines:])


def make_image(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=520, height=180)
    page.insert_text((30, 65), "智能文档管理系统", fontname="china-s", fontsize=30)
    page.insert_text((30, 130), "OCR SMOKE 2026", fontname="helv", fontsize=30)
    path.write_bytes(page.get_pixmap(dpi=180).tobytes("png"))
    doc.close()


def main() -> int:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    storage_dir = RUN_DIR / "storage"
    image_path = RUN_DIR / "ocr-smoke.png"
    make_image(image_path)
    say(f"run dir: {RUN_DIR}")

    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": DATABASE_URL,
            "OPENSEARCH_URL": OPENSEARCH_URL,
            "CLIP_SERVICE_URL": "http://127.0.0.1:8001",
            "JWT_SECRET": "ocr-smoke-only-secret-0123456789abcdef",
            "STORAGE_ROOT": str(storage_dir),
            "OPENSEARCH_INDEX_PREFIX": INDEX_PREFIX,
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
            "WORKER_MAX_TASKS": "50",
            "WORKER_POLL_SECONDS": "0.5",
        }
    )

    handles = []
    processes: list[tuple[str, subprocess.Popen]] = []

    def start(
        name: str,
        args: list[str],
        cwd: Path,
        log_name: str,
        extra: dict[str, str] | None = None,
    ):
        child_env = env.copy()
        if extra:
            child_env.update(extra)
        handle = open(RUN_DIR / log_name, "w", encoding="utf-8")
        handles.append(handle)
        process = subprocess.Popen(
            args,
            cwd=str(cwd),
            env=child_env,
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
        processes.append((name, process))
        say(f"started {name} (pid {process.pid})")
        return process

    def stop_all() -> None:
        for name, process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                say(f"stopped {name}")
        for handle in handles:
            handle.close()

    api_log = RUN_DIR / "api.log"
    worker_log = RUN_DIR / "backend-worker.log"
    ocr_log = RUN_DIR / "ocr-worker.log"
    try:
        start(
            "api",
            [
                str(MAIN_PY),
                "-m",
                "uvicorn",
                "app.main:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(API_PORT),
            ],
            BACKEND_DIR,
            api_log.name,
        )
        start("backend-worker", [str(MAIN_PY), "-m", "app.worker"], BACKEND_DIR, worker_log.name)

        with httpx.Client(base_url=API_URL, timeout=20.0) as client:
            def healthy() -> dict | None:
                response = client.get("/health")
                if response.status_code != 200:
                    return None
                data = response.json()
                if data["database"]["status"] == "ok" and data["opensearch"]["status"] == "ok":
                    return data
                return None

            health = wait_for("API health", healthy, 90)
            say(
                "health ok: database={}, opensearch={}, clip={}".format(
                    health["database"]["status"],
                    health["opensearch"]["status"],
                    health["clip_service"]["status"],
                )
            )

            username = "ocrsmoke_" + uuid.uuid4().hex[:8]
            password = "SmokePass2026!"
            response = client.post(
                "/api/auth/register", json={"username": username, "password": password}
            )
            response.raise_for_status()
            response = client.post(
                "/api/auth/login", json={"username": username, "password": password}
            )
            response.raise_for_status()
            headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
            say(f"registered and logged in as {username}")

            response = client.post(
                "/api/documents",
                headers=headers,
                files={"file": ("ocr-smoke.png", image_path.read_bytes(), "image/png")},
            )
            response.raise_for_status()
            document = response.json()
            document_id = document["id"]
            say(f"uploaded document {document_id}")

            def parsed() -> dict | None:
                item = client.get(f"/api/documents/{document_id}", headers=headers)
                if item.status_code != 200:
                    return None
                data = item.json()
                if data["status"] == "failed":
                    raise RuntimeError("parse task failed")
                return data if data["status"] == "succeeded" else None

            wait_for("parse task", parsed, 120)
            say("parse task succeeded")

            tasks = client.get(f"/api/documents/{document_id}/tasks", headers=headers).json()[
                "items"
            ]
            ocr_tasks = [task for task in tasks if task["task_type"] == "ocr"]
            if not ocr_tasks:
                raise RuntimeError("parse succeeded but no OCR task was created")
            say(f"OCR task queued: {ocr_tasks[0]['id']}")

            ocr_process = start(
                "ocr-worker",
                [str(OCR_PY), "-m", "ocr_worker"],
                OCR_DIR,
                ocr_log.name,
                {"OCR_WORKER_MAX_TASKS": "1", "OCR_WORKER_POLL_SECONDS": "0.5"},
            )
            try:
                returncode = ocr_process.wait(timeout=300)
            except subprocess.TimeoutExpired:
                ocr_process.kill()
                raise RuntimeError("OCR worker timed out")
            if returncode != 0:
                raise RuntimeError(f"OCR worker exited with {returncode}\n{log_tail(ocr_log)}")
            say("OCR worker exited successfully")

            def ocr_succeeded() -> dict | None:
                items = client.get(
                    f"/api/documents/{document_id}/tasks", headers=headers
                ).json()["items"]
                for task in items:
                    if task["task_type"] != "ocr":
                        continue
                    if task["status"] == "failed":
                        raise RuntimeError(f"OCR task failed: {task.get('error')}")
                    if task["status"] == "succeeded":
                        return task
                return None

            wait_for("OCR task completion", ocr_succeeded, 30)
            say("OCR task succeeded")

            def ocr_text() -> str | None:
                response = client.get(
                    f"/api/documents/{document_id}/text",
                    params={"source_type": "ocr", "page_size": 100},
                    headers=headers,
                )
                response.raise_for_status()
                text = "".join(item["text"] for item in response.json()["items"])
                normalized = "".join(text.split())
                if "智能文档管理系统" in normalized and "2026" in normalized:
                    return text
                return None

            recognized = wait_for("OCR text in database", ocr_text, 30)
            say(f"OCR text stored: {recognized!r}")

            search_body = {
                "query": "智能文档管理系统",
                "top_k": 10,
                "channels": {"meta": False, "text": True, "image": False},
                "source_types": ["ocr"],
            }

            def search_hit() -> dict | None:
                response = client.post("/api/search", json=search_body, headers=headers)
                response.raise_for_status()
                for hit in response.json()["hits"]:
                    if hit["document"]["id"] == document_id:
                        return hit
                return None

            hit = wait_for("OCR search hit", search_hit, 60)
            evidence = hit.get("evidence") or {}
            if evidence.get("source_type") != "ocr":
                raise RuntimeError(f"search hit did not come from OCR chunk: {evidence}")
            say(
                "search hit via OCR chunk: {} (snippet={!r})".format(
                    evidence.get("chunk_id"), evidence.get("snippet", "")[:120]
                )
            )

            response = client.delete(f"/api/documents/{document_id}", headers=headers)
            if response.status_code != 204:
                raise RuntimeError(f"delete returned {response.status_code}")

            wait_for(
                "document deletion",
                lambda: True
                if client.get(f"/api/documents/{document_id}", headers=headers).status_code == 404
                else None,
                20,
            )

            def no_ocr_chunks() -> bool | None:
                response = httpx.post(
                    f"{OPENSEARCH_URL}/{INDEX_PREFIX}chunks/_count",
                    json={"query": {"term": {"document_id": document_id}}},
                    timeout=5.0,
                )
                if response.status_code >= 400:
                    return None
                return True if response.json().get("count", 0) == 0 else None

            wait_for("cleanup of OCR chunks", no_ocr_chunks, 60)
            say("document deleted and OCR chunks removed")

            response = client.post("/api/search", json=search_body, headers=headers)
            response.raise_for_status()
            still_listed = [
                item for item in response.json()["hits"] if item["document"]["id"] == document_id
            ]
            if still_listed:
                raise RuntimeError("deleted document is still searchable")
            say("deleted document is no longer searchable")

    except Exception as exc:
        print(f"FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        for name, path in (
            ("api", api_log),
            ("backend-worker", worker_log),
            ("ocr-worker", ocr_log),
        ):
            print(f"--- {name} log tail ---\n{log_tail(path)}", file=sys.stderr)
        return 1
    finally:
        stop_all()
        try:
            response = httpx.delete(
                f"{OPENSEARCH_URL}/{INDEX_PREFIX}doc_meta,{INDEX_PREFIX}chunks", timeout=10.0
            )
            if response.status_code < 400:
                say(f"removed smoke indices with prefix {INDEX_PREFIX}")
        except Exception:
            pass

    say("PASS: real OCR end-to-end chain is working")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
