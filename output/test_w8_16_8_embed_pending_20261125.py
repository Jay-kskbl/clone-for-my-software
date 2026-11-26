from __future__ import annotations

import json
import secrets
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx


ROOT = Path(r"C:\Users\lenovo\Desktop\my-software-main\_gh_upload")
OUT = ROOT / "output" / "w8-16.8-no-clip-no-ocr-20261125"
BASE = "http://127.0.0.1:8000"
CONTROL = ROOT / "experiments" / "docvqa" / "datasets" / "files" / "docvqa" / "ffhv0228.jpg"

OUT.mkdir(parents=True, exist_ok=True)
username = f"w8ctrl_{secrets.token_hex(4)}"
password = secrets.token_urlsafe(24)

with httpx.Client(base_url=BASE, timeout=httpx.Timeout(60.0, connect=10.0)) as client:
    response = client.post("/api/auth/register", json={"username": username, "password": password})
    response.raise_for_status()
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    response.raise_for_status()
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}

    with CONTROL.open("rb") as handle:
        upload = client.post(
            "/api/documents",
            headers=headers,
            files={"file": (CONTROL.name, handle, "image/jpeg")},
        )
    upload.raise_for_status()
    document_id = upload.json()["id"]

    snapshots = []
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        document = client.get(f"/api/documents/{document_id}", headers=headers).json()
        tasks = client.get(f"/api/documents/{document_id}/tasks", headers=headers).json()["items"]
        snapshot = {
            "at": datetime.now(UTC).isoformat(),
            "status": document["status"],
            "tasks": [
                {
                    "type": task["task_type"],
                    "status": task["status"],
                    "attempts": task["attempts"],
                    "max_attempts": task["max_attempts"],
                    "error": task["error"],
                }
                for task in tasks
            ],
        }
        snapshots.append(snapshot)
        task_map = {task["type"]: task for task in snapshot["tasks"]}
        if (
            task_map.get("embed", {}).get("status") in {"pending", "failed"}
            and task_map.get("embed", {}).get("attempts") == 3
            and task_map.get("ocr", {}).get("status") == "pending"
        ):
            break
        time.sleep(3)

    result = {
        "username": username,
        "document_id": document_id,
        "filename": CONTROL.name,
        "snapshots": snapshots,
        "final": snapshots[-1],
    }
    (OUT / "summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(result["final"], ensure_ascii=False, indent=2))
