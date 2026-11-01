"""v0.4 acceptance: one gateway, no SDKs, and no model path outside it."""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[2] / "src/backend"
GATEWAY = SRC / "infrastructure/llm_client.py"
SDKS = {"openai", "anthropic", "litellm", "langchain", "dashscope", "zhipuai", "google"}


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots |= {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_only_the_gateway_imports_an_http_client_and_nobody_imports_an_sdk():
    assert GATEWAY.is_file()
    for path in SRC.rglob("*.py"):
        roots = imported_roots(path)
        assert not roots & SDKS, path
        if path != GATEWAY:
            assert not roots & {"httpx", "httpx2", "requests", "aiohttp", "urllib3"}, path


def test_domain_imports_nothing_outside_the_domain():
    for path in (SRC / "domain").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(
                    ("backend.application", "backend.infrastructure", "backend.api")
                ), path
            assert not (isinstance(node, ast.ImportFrom) and node.module == "sqlalchemy"), path
