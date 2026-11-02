"""v0.3 acceptance: publication checks of schema 3 (spec section 2.2).

Each mutation breaks exactly one rule of the official case file; parse_case must refuse it.
"""

import copy
import json

import pytest

from backend.application.case import content_hash, default_case_path, load_case, parse_case

pytestmark = [pytest.mark.unit, pytest.mark.rule]

OFFICIAL = json.loads(default_case_path().read_text(encoding="utf-8"))


def find(items, item_id):
    return next(item for item in items if item["id"] == item_id)


def action(case, action_id):
    return next(a for s in case["scenes"] for a in s["actions"] if a["id"] == action_id)


def _remove_a04(c):
    find(c["scenes"], "S01")["actions"] = [
        a for a in find(c["scenes"], "S01")["actions"] if a["id"] != "A04"
    ]


def _lie_in_two_chains(c):
    c["lie_chains"].append({"id": "CH04", "npc_id": "NPC02", "lie_ids": ["L03"]})


def _effect_on_two_layers(c):
    l02 = find(c["lies"], "L02")
    l02["admission_presented"]["all_of"] = ["E01", "E02", "E08"]
    l02["effects"].append({"evidence_id": "E01", "pressure": 5, "trust": 0})


def _orphan_admitted_knowledge(c):
    c["knowledge"].append(
        {"id": "K12", "content": "多余的承认。", "known_by": ["NPC02"], "disclosure": "ADMITTED"}
    )


def _asymmetric_conflict(c):
    find(c["timeline"], "T05")["conflicts_with"] = []


MUTATIONS = {
    "duplicate_character": lambda c: c["characters"][1].update(id="NPC01"),
    "duplicate_action_across_scenes": lambda c: action(c, "A05").update(id="A01"),
    "duplicate_evidence": lambda c: c["evidence"][1].update(id="E01"),
    "duplicate_knowledge": lambda c: c["knowledge"][1].update(id="K01"),
    "duplicate_lie": lambda c: c["lies"][1].update(id="L01"),
    "duplicate_relationship": lambda c: c["relationships"][1].update(id="R01"),
    "duplicate_timeline": lambda c: c["timeline"][1].update(id="T01"),
    "action_grants_unknown_evidence": lambda c: action(c, "A04").update(evidence_id="E99"),
    "scene_unlock_unknown_evidence": lambda c: find(c["scenes"], "S03")["unlock"].update(
        all_of=["E99"]
    ),
    "evidence_never_granted": _remove_a04,
    "cycle_without_entry": lambda c: action(c, "A07")["requires"].update(all_of=["E09"]),
    "scene_needs_its_own_evidence": lambda c: find(c["scenes"], "S03")["unlock"].update(
        all_of=["E08"]
    ),
    "no_open_start_scene": lambda c: find(c["scenes"], "S01")["unlock"].update(any_of=["E05"]),
    "interrogatable_without_pressure": lambda c: find(c["characters"], "NPC02").update(
        initial_pressure=None
    ),
    "interrogatable_without_personality": lambda c: find(c["characters"], "NPC03").update(
        personality=None
    ),
    "suspect_not_interrogatable": lambda c: c["suspects"].append({"id": "VICTIM", "label": "陆衡"}),
    "chainless_npc_without_default_reply": lambda c: find(c["characters"], "NPC04").update(
        default_reply=None
    ),
    "lie_of_victim": lambda c: (
        find(c["lies"], "L03").update(npc_id="VICTIM"),
        find(c["lie_chains"], "CH02").update(npc_id="VICTIM"),
    ),
    "lie_outside_any_chain": lambda c: find(c["lie_chains"], "CH01").update(lie_ids=["L01"]),
    "lie_in_two_chains": _lie_in_two_chains,
    "chain_npc_mismatch": lambda c: find(c["lie_chains"], "CH02").update(npc_id="NPC03"),
    "empty_chain": lambda c: c["lie_chains"].append(
        {"id": "CH04", "npc_id": "NPC04", "lie_ids": []}
    ),
    "empty_counterevidence": lambda c: find(c["lies"], "L03").update(
        counterevidence={"all_of": [], "any_of": []}
    ),
    "no_psychological_threshold": lambda c: find(c["lies"], "L04").update(
        admission_pressure_min=None
    ),
    "admission_reveals_asked_knowledge": lambda c: find(c["lies"], "L03").update(
        admitted_knowledge_id="K07"
    ),
    "admitted_knowledge_without_lie": _orphan_admitted_knowledge,
    "effect_outside_layer": lambda c: find(c["lies"], "L03")["effects"].append(
        {"evidence_id": "E07", "pressure": 5, "trust": 0}
    ),
    "effect_on_two_layers_of_one_npc": _effect_on_two_layers,
    "core_lie_of_someone_else": lambda c: find(c["characters"], "NPC02").update(
        core_lie_ids=["L03", "L04"]
    ),
    "single_layer_unreachable": lambda c: find(c["lies"], "L04").update(admission_pressure_min=70),
    "second_layer_unreachable": lambda c: find(c["lies"], "L02").update(admission_pressure_min=95),
    "trust_only_path_from_worst_trust": lambda c: find(c["lies"], "L03").update(
        admission_pressure_min=None, admission_trust_min=30
    ),
    "topic_for_admitted_knowledge": lambda c: find(c["interrogation"]["topics"], "Q02").update(
        knowledge_id="K05"
    ),
    "asked_knowledge_without_topic": lambda c: c["interrogation"].update(
        topics=[t for t in c["interrogation"]["topics"] if t["id"] != "Q05"]
    ),
    "contradiction_with_wrong_speaker": lambda c: find(
        c["interrogation"]["contradictions"], "C03"
    ).update(npc_id="NPC01"),
    "contradiction_on_unverified_evidence": lambda c: find(
        c["interrogation"]["contradictions"], "C03"
    ).update(evidence_id="E09"),
    "contradiction_on_public_knowledge": lambda c: find(
        c["interrogation"]["contradictions"], "C01"
    ).update(knowledge_id="K01"),
    "public_relationship_with_reveal": lambda c: find(c["relationships"], "R01").update(
        reveal_evidence_ids=["E01"]
    ),
    "evidence_source_not_revealing": lambda c: find(c["relationships"], "R05").update(
        source_id="E01"
    ),
    "relationship_unknown_endpoint": lambda c: find(c["relationships"], "R04").update(
        to_id="NPC09"
    ),
    "exact_time_with_range": lambda c: find(c["timeline"], "T01").update(end_minutes=1161),
    "range_backwards": lambda c: find(c["timeline"], "T04").update(start_minutes=1279),
    "unknown_time_with_minutes": lambda c: find(c["timeline"], "T07").update(start_minutes=1272),
    "conflict_with_itself": lambda c: find(c["timeline"], "T06").update(conflicts_with=["T06"]),
    "asymmetric_conflict": _asymmetric_conflict,
    "timeline_unknown_participant": lambda c: find(c["timeline"], "T02").update(
        participant_ids=["NPC09"]
    ),
    "scores_do_not_sum_to_100": lambda c: c["scoring"]["criteria"][0].update(points=35),
    "support_on_unverified_evidence": lambda c: find(c["scoring"]["criteria"], "C_STAGE")[
        "evidence_ids"
    ].append("E09"),
    "truth_unknown_step": lambda c: c["truth"].update(steps=["P_ENTER", "P_FLY"]),
    "guessing_reaches_correct": lambda c: c["scoring"].update(correct_min=75),
    "unknown_field": lambda c: c.update(rules_tree={}),
    "old_schema_version": lambda c: c.update(schema_version=2),
    "bad_evidence_kind": lambda c: c["evidence"][0].update(kind="VIDEO"),
}


def test_official_case_is_valid_and_complete():
    case = load_case()
    assert (case.schema_version, case.scope, case.version) == (3, "full_case", "3-full")
    assert len([c for c in case.characters if c.interrogatable]) == 4
    assert len(case.scenes) == 4
    assert len(case.evidence) == 12
    assert len([e for e in case.evidence if e.is_key]) == 5
    assert len(case.lie_chains) == 3
    assert max(len(chain.lie_ids) for chain in case.lie_chains) == 2


@pytest.mark.parametrize("name", sorted(MUTATIONS))
def test_publication_rejects(name):
    broken = copy.deepcopy(OFFICIAL)
    MUTATIONS[name](broken)
    with pytest.raises(ValueError):
        parse_case(json.dumps(broken, ensure_ascii=False))


def test_cycle_with_an_external_entry_is_accepted():
    changed = copy.deepcopy(OFFICIAL)
    action(changed, "A05")["requires"] = {"all_of": [], "any_of": ["E06", "E02"]}
    parse_case(json.dumps(changed, ensure_ascii=False))


def test_array_order_of_definitions_does_not_change_the_hash():
    shuffled = copy.deepcopy(OFFICIAL)
    shuffled["knowledge"].reverse()
    assert content_hash(parse_case(json.dumps(shuffled, ensure_ascii=False))) == content_hash(
        load_case()
    )


def test_duplicate_json_keys_are_rejected():
    text = default_case_path().read_text(encoding="utf-8")
    duplicated = text.replace('"title": "停电之夜",', '"title": "停电之夜",\n  "title": "别的",', 1)
    assert duplicated != text
    with pytest.raises(ValueError):
        parse_case(duplicated)
