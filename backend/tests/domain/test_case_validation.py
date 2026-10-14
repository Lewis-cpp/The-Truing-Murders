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
        lambda c: c["knowledge"][2].update({"disclosure": "OVERHEARD"}),
        lambda c: c["interrogation"].update({"irrelevant_trust": 5}),
        lambda c: c["interrogation"].update({"evade_after": 0}),
        lambda c: c["interrogation"].update({"topics": []}),
        lambda c: c["interrogation"]["topics"][0].update({"knowledge_id": "UNKNOWN"}),
        lambda c: c["interrogation"]["topics"][0].update({"knowledge_id": "K02"}),
        lambda c: c["interrogation"]["topics"][0].update({"npc_id": "NPC02"}),
        lambda c: c["interrogation"]["contradictions"][0].update({"knowledge_id": "K01"}),
        lambda c: c["interrogation"]["contradictions"][0].update({"evidence_id": "UNKNOWN"}),
        lambda c: c["interrogation"]["contradictions"][0].update({"pressure": -15}),
        lambda c: c["interrogation"]["contradictions"].append(
            {**c["interrogation"]["contradictions"][0], "id": "C02"}
        ),
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
    assert load_case().version == "2-slice"
    invalid = tmp_path / "broken.json"
    invalid.write_text("{broken")
    with pytest.raises(ValueError, match="结构校验失败"):
        load_case(invalid)


def test_costs_that_could_block_the_admission_are_rejected(tmp_path, raw):
    # A trust path of 30 survives the initial values but not every cost paid first.
    raw["lie"].update({"admission_pressure_min": None, "admission_trust_min": 30})
    with pytest.raises(ValueError, match="代价"):
        load_case(write_case(tmp_path, raw))
    raw["interrogation"]["irrelevant_trust"] = 0
    assert load_case(write_case(tmp_path, raw)).lie.admission_trust_min == 30


def test_irrelevant_evidence_counts_toward_the_worst_case_cost(tmp_path, raw):
    # Two wrong pairings leave 30 trust and E01 costs 5, so a trust path of 25 holds...
    raw["lie"].update({"admission_pressure_min": None, "admission_trust_min": 25})
    assert load_case(write_case(tmp_path, raw)).lie.admission_trust_min == 25
    # ...until E02 is no longer part of the lie and presenting it may cost 5 more first.
    raw["lie"]["effects"] = [e for e in raw["lie"]["effects"] if e["evidence_id"] != "E02"]
    with pytest.raises(ValueError, match="代价"):
        load_case(write_case(tmp_path, raw))


def test_contradiction_needs_verified_evidence(tmp_path, raw):
    contradiction = raw["interrogation"]["contradictions"][0]
    contradiction["evidence_id"] = "E02"
    assert load_case(write_case(tmp_path, raw)).interrogation.contradictions[0].evidence_id == "E02"
    raw["evidence"][1]["credibility"] = "UNVERIFIED"
    raw["scoring"]["criteria"][5]["evidence_ids"] = ["E01"]
    raw["scoring"]["criteria"][5]["step_id"] = "P_ENTER"
    with pytest.raises(ValueError, match="矛盾所依据"):
        load_case(write_case(tmp_path, raw))
