import json

import pytest

from backend.application.case import default_case_path, load_case
from backend.domain.models import Dependency

pytestmark = pytest.mark.unit


@pytest.fixture
def raw():
    return json.loads(default_case_path().read_text())


def write_case(tmp_path, raw):
    path = tmp_path / "case.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    "mutation",
    [
        lambda c: c.update({"unsupported_rule": "grant_everything"}),
        lambda c: c["npc"].update({"initial_pressure": 101}),
        lambda c: c["npc"].update({"initial_trust": True}),
        lambda c: c["scene"]["actions"][0].update({"evidence_id": "UNKNOWN"}),
        lambda c: c["scene"]["actions"][0]["requires"].update({"all_of": ["UNKNOWN"]}),
        lambda c: c["evidence"][1].update({"id": "E01"}),
        lambda c: c["knowledge"][1].update({"known_by": ["NPC02"]}),
        lambda c: c["knowledge"][1].update({"known_by": ["UNKNOWN"]}),
        lambda c: c["lie"].update({"counterevidence": {"all_of": [], "any_of": []}}),
        lambda c: c["lie"].update({"admitted_knowledge_id": "UNKNOWN"}),
        lambda c: c["lie"].update({"admission_pressure_min": None, "admission_trust_min": None}),
        lambda c: c["lie"].update({"admission_pressure_min": 100}),
        lambda c: c["truth"].update({"culprit": "UNKNOWN"}),
        lambda c: c["truth"].update({"steps": []}),
        lambda c: c["scoring"].update({"process_order": "guess"}),
        lambda c: c["scoring"].update({"correct_min": 30}),
        lambda c: c["scoring"].update({"correct_min": 75}),
        lambda c: c["scoring"]["criteria"][0].update({"points": 31}),
        lambda c: c["scoring"]["criteria"][4].update({"evidence_ids": []}),
        lambda c: c["scoring"]["criteria"][4].update({"step_id": "UNKNOWN"}),
        lambda c: c["evidence"][0].update({"credibility": "UNVERIFIED"}),
    ],
)
def test_bad_case_is_rejected_at_load(tmp_path, raw, mutation):
    mutation(raw)
    with pytest.raises(ValueError):
        load_case(write_case(tmp_path, raw))


def test_blocking_cycle_rejected_and_any_external_entry_accepted(tmp_path, raw):
    raw["scene"]["actions"][0]["requires"] = {"all_of": ["E03"], "any_of": []}
    with pytest.raises(ValueError, match="循环依赖"):
        load_case(write_case(tmp_path, raw))
    raw["scene"]["actions"][0]["requires"] = {"all_of": [], "any_of": ["E03", "E02"]}
    assert load_case(write_case(tmp_path, raw)).case_id == "case_001"


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
    assert load_case().version == "1-slice"
    invalid = tmp_path / "broken.json"
    invalid.write_text("{broken")
    with pytest.raises(ValueError, match="结构校验失败"):
        load_case(invalid)
