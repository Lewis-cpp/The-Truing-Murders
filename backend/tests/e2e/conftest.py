"""Browser end-to-end fixtures: a real uvicorn on the test database and `vite preview`.

Run with: uv run pytest tests/e2e -m e2e   (needs `npm run build` and Playwright Chromium)
"""

import os
import socket
import subprocess
import time
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[3] / "frontend"
BACKEND = Path(__file__).resolve().parents[2]
WEB = "http://127.0.0.1:4173"


def wait_for(port: int, process: subprocess.Popen, seconds: float = 30) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"process exited early with {process.returncode}")
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.2)
    raise RuntimeError(f"port {port} did not open")


@pytest.fixture(scope="session")
def servers(migrated_url):
    assert (FRONTEND / "dist/index.html").is_file(), "run `npm run build` in frontend/ first"
    env = {
        **os.environ,
        "DATABASE_URL": migrated_url,
        "LLM_ENABLED": "false",
        "ALLOWED_ORIGINS": f'["{WEB}"]',
        "COOKIE_SECURE": "false",
    }
    api = subprocess.Popen(
        [
            "uv",
            "run",
            "--offline",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        cwd=BACKEND,
        env=env,
    )
    # Start vite directly: terminating the npm wrapper orphans the actual server
    # and the next run finds the port busy.
    web = subprocess.Popen([str(FRONTEND / "node_modules/.bin/vite"), "preview"], cwd=FRONTEND)
    try:
        wait_for(8000, api)
        wait_for(4173, web)
        yield WEB
    finally:
        for process in (web, api):
            process.terminate()
            process.wait(timeout=10)


@pytest.fixture
def page(servers, db):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1366, "height": 768})
        page = context.new_page()
        page.set_default_timeout(10_000)
        page.goto(servers)
        yield page
        browser.close()
