"""v0.6 acceptance: every functional requirement is traced to code and an existing test."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TABLE = ROOT / "docs/traceability.md"


def test_every_requirement_has_a_row_with_existing_tests():
    text = TABLE.read_text(encoding="utf-8")
    rows = {m.group(1): m.group(0) for m in re.finditer(r"^\| ((?:N)?FR-\d{2}) \|.*$", text, re.M)}
    expected = [f"FR-{i:02d}" for i in range(1, 20)] + [f"NFR-{i:02d}" for i in range(1, 12)]
    assert sorted(rows) == sorted(expected)
    for requirement, row in rows.items():
        paths = re.findall(r"`((?:backend|frontend)/tests/[^`]+)`", row)
        if requirement.startswith("FR-"):
            assert paths, f"{requirement} has no automated test"
        for path in paths:
            assert (ROOT / path.split("::")[0]).is_file(), f"{requirement}: {path} does not exist"
