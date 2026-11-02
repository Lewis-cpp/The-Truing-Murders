"""v1.0 acceptance: release hygiene that a reviewer would otherwise check by hand."""

import ast
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND_TESTS = ROOT / "backend/tests"
FRONTEND_TESTS = ROOT / "frontend/tests"


def tracked() -> list[str]:
    return subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()


def test_every_skip_or_xfail_states_a_reason():
    for path in BACKEND_TESTS.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = ast.unparse(node.func)
            if name.endswith(
                ("mark.skip", "mark.skipif", "mark.xfail", "pytest.skip", "pytest.xfail")
            ):
                has_reason = any(k.arg == "reason" for k in node.keywords) or (
                    name.endswith(("pytest.skip", "pytest.xfail")) and node.args
                )
                assert has_reason, f"{path}:{node.lineno} {name} without a reason"
            assert not name.endswith("mark.xfail"), f"{path}:{node.lineno} xfail is not allowed"


def test_frontend_tests_have_no_focus_or_skip():
    for path in FRONTEND_TESTS.rglob("*.ts"):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\b(it|describe|test)\.(only|skip)\(", text), path


@pytest.mark.parametrize(
    "command",
    [
        "uv sync --locked",
        "docker compose up -d --wait",
        "uv run alembic upgrade head",
        "uv run python -m backend.import_case assets/cases/case_001/v1/case.json",
        "uv run pytest",
        "uv run alembic check",
        "npm ci",
        "npm run build",
        "npm test",
        "pytest tests/e2e -m e2e",
        "pytest tests/performance -m performance",
        "RUN_LIVE_LLM_TESTS=1",
        "pg_dump",
        "pg_restore",
    ],
)
def test_readme_documents_the_release_commands(command):
    assert command in (ROOT / "README.md").read_text(encoding="utf-8")


def test_generated_output_and_secrets_are_not_tracked():
    files = tracked()
    for path in files:
        name = Path(path).name
        assert not (name == ".env" or (name.startswith(".env.") and name != ".env.example")), path
        assert not path.startswith(("backend/reports/", "frontend/dist/")), path
        assert not path.endswith((".dump", ".sqlite", ".db")), path
    ignored = subprocess.run(
        [
            "git",
            "check-ignore",
            "backend/reports/x.json",
            "frontend/dist/index.html",
            "backend/.env",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout.split()
    assert ignored == ["backend/reports/x.json", "frontend/dist/index.html", "backend/.env"]


def test_no_credentials_in_tracked_text():
    pattern = re.compile(
        r"(sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
    )
    for path in tracked():
        file = ROOT / path
        if file.suffix in {".png", ".jpg", ".woff2", ".lock"} or not file.is_file():
            continue
        try:
            text = file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        assert not pattern.search(text), path


def test_delivery_records_exist_for_every_release():
    docs = ROOT / "docs"
    for name in (
        "19-v0.3-delivery.md",
        "20-v0.4-delivery.md",
        "21-v0.5-delivery.md",
        "22-v0.6-delivery.md",
        "23-v1.0-delivery.md",
        "test-report.md",
        "traceability.md",
    ):
        assert (docs / name).is_file(), name
