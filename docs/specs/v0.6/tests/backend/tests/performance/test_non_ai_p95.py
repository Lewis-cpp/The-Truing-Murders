"""v0.6 performance: 5 concurrent sessions of non-AI operations against a real uvicorn.

    uv run pytest tests/performance -m performance -q

Writes backend/reports/performance/p95-<time>.json with the environment and samples.
"""

import json
import os
import platform
import statistics
import subprocess
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx2
import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.performance

BACKEND = Path(__file__).resolve().parents[2]
PORT = 8011
BASE = f"http://127.0.0.1:{PORT}"
ORIGIN = "http://127.0.0.1:4173"
SESSIONS = 5


def play(timings: list[float], errors: list[str]) -> None:
    with httpx2.Client(base_url=BASE, headers={"Origin": ORIGIN}, timeout=30) as client:
        client.post("/api/v1/visitors", json={})
        version = None
        session = None

        def write(method, path, body=None):
            nonlocal version, session
            headers = {"Idempotency-Key": str(uuid.uuid4())}
            if version is not None:
                headers["X-Expected-State-Version"] = str(version)
            started = time.perf_counter()
            response = client.request(method, path, json=body, headers=headers)
            timings.append(time.perf_counter() - started)
            if response.status_code >= 300:
                errors.append(f"{method} {path} {response.status_code} {response.text[:200]}")
                return
            data = response.json()
            version, session = data["result_state_version"], data["session_id"]

        cases = client.get("/api/v1/cases").json()["items"]
        write(
            "POST",
            "/api/v1/sessions",
            {"case_id": "case_001", "case_version": cases[0]["case_version"]},
        )
        scenes = {
            "A01": "S01",
            "A02": "S01",
            "A03": "S01",
            "A04": "S01",
            "A05": "S02",
            "A06": "S02",
            "A07": "S03",
            "A08": "S03",
            "A09": "S03",
            "A10": "S04",
            "A11": "S04",
            "A12": "S04",
        }
        for action, scene in scenes.items():
            write(
                "POST",
                f"/api/v1/sessions/{session}/scenes/{scene}/investigations",
                {"action_id": action},
            )
        write("PUT", f"/api/v1/sessions/{session}/interrogation", {"npc_id": "NPC01"})
        for evidence in ("E01", "E03", "E02", "E08"):
            write(
                "POST",
                f"/api/v1/sessions/{session}/npcs/NPC01/evidence-presentations",
                {"evidence_id": evidence},
            )
        started = time.perf_counter()
        client.get(f"/api/v1/sessions/{session}")
        timings.append(time.perf_counter() - started)
        write("PUT", f"/api/v1/sessions/{session}/accusation-preparation", {})
        content = {
            "suspect_character_id": "NPC01",
            "weapon_option_id": "W01",
            "motive_option_id": "M01",
            "ordered_process_step_ids": ["P_ENTER", "P_ATTACK", "P_STAGE"],
            "cited_evidence_ids": ["E01", "E02", "E03"],
            "step_evidence_links": [],
            "explanation": "",
        }
        write(
            "POST", f"/api/v1/sessions/{session}/accusation", {"content": content, "confirm": True}
        )


def test_five_sessions_p95_under_one_second(db, migrated_url):
    env = {
        **os.environ,
        "DATABASE_URL": migrated_url,
        "LLM_ENABLED": "false",
        "ALLOWED_ORIGINS": f'["{ORIGIN}"]',
        "COOKIE_SECURE": "false",
    }
    server = subprocess.Popen(
        [
            "uv",
            "run",
            "--offline",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(PORT),
            "--log-level",
            "warning",
        ],
        cwd=BACKEND,
        env=env,
    )
    try:
        for _ in range(150):
            try:
                if httpx2.get(f"{BASE}/api/v1/health").status_code == 200:
                    break
            except httpx2.TransportError:
                time.sleep(0.2)
        timings: list[float] = []
        errors: list[str] = []
        threads = [threading.Thread(target=play, args=(timings, errors)) for _ in range(SESSIONS)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        server.terminate()
        server.wait(timeout=10)
    assert errors == []
    ordered = sorted(timings)
    p95 = ordered[int(0.95 * (len(ordered) - 1))]
    with create_engine(migrated_url).connect() as connection:
        postgres = connection.execute(text("SHOW server_version")).scalar_one()
    report = {
        "samples": len(timings),
        "sessions": SESSIONS,
        "p50_ms": round(statistics.median(timings) * 1000, 1),
        "p95_ms": round(p95 * 1000, 1),
        "max_ms": round(ordered[-1] * 1000, 1),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "postgres": postgres,
    }
    out = BACKEND / "reports/performance"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    (out / f"p95-{stamp}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert len(timings) == SESSIONS * 21
    assert p95 <= 1.0, report
