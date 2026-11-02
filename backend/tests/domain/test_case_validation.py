"""Ported v0.2 checks: Dependency semantics, loader independence, structural rejection.

The slice-specific publication mutations were superseded by the schema-3 acceptance tests
(tests/domain/test_case_v3_validation.py); see docs/specs/v0.3/test-amendments.md.
"""

import json

import pytest

from backend.application.case import default_case_path, load_case
from backend.domain.models import Dependency

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "held,expected",
    [([], False), (["A"], False), (["B"], False), (["A", "B"], True), (["A", "C"], True)],
)
def test_all_and_any_are_combined(held, expected):
    dependency = Dependency(all_of=("A",), any_of=("B", "C"))
    assert dependency.satisfied(frozenset(held)) is expected


def test_empty_dependencies_mean_no_prerequisites():
    assert Dependency(all_of=(), any_of=()).satisfied(frozenset())


def test_loading_is_independent_of_cwd_and_rejects_non_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_case().version == "3-full"
    invalid = tmp_path / "broken.json"
    invalid.write_text("{broken")
    with pytest.raises(ValueError, match="结构校验失败"):
        load_case(invalid)


def test_missing_file_is_a_value_error(tmp_path):
    with pytest.raises(ValueError, match="读取失败"):
        load_case(tmp_path / "nope.json")


def test_official_file_round_trips_through_parse():
    text = default_case_path().read_text(encoding="utf-8")
    assert load_case().title == "停电之夜"
    assert json.loads(text)["schema_version"] == 3
