"""v0.3 acceptance: read-only resources show only what the player knows and never write."""

import pytest
from player import EMPTY_DRAFT, Player

pytestmark = [pytest.mark.api, pytest.mark.integration]


def code(response) -> str:
    return response.json()["error"]["code"]


def data(response):
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"session_id", "state_version", "data"}
    return body["data"]


@pytest.fixture
def player(client):
    player = Player(client)
    player.start()
    return player


def test_scenes_open_with_evidence_and_locked_ones_look_missing(player):
    assert [s["scene_id"] for s in data(player.get("/scenes"))["items"]] == ["S01"]
    locked = player.get("/scenes/S02")
    assert (locked.status_code, code(locked)) == (404, "SCENE_NOT_FOUND")
    missing = player.get("/scenes/S99")
    assert missing.json()["error"]["message"] == locked.json()["error"]["message"]
    player.investigate("A01")
    scene = data(player.get("/scenes/S02"))
    assert scene["scene_id"] == "S02"
    assert [a["action_id"] for a in scene["actions"]] == ["A05", "A06"]
    a06 = scene["actions"][1]
    assert (a06["enabled"], a06["disabled_reason"]) == (False, "核对条件尚不齐全。")
    assert "E05" not in a06["disabled_reason"]


def test_investigation_url_must_match_an_open_scene(player):
    locked = player.investigate("A07", scene_id="S03")
    assert (locked.status_code, code(locked)) == (404, "SCENE_NOT_FOUND")
    player.investigate("A01")
    elsewhere = player.investigate("A05", scene_id="S01")
    assert (elsewhere.status_code, code(elsewhere)) == (422, "INVALID_ACTION_REFERENCE")
    assert player.investigate("A05", scene_id="S02").status_code == 201
    unready = player.investigate("A11")
    assert (unready.status_code, code(unready)) == (409, "ACTION_UNAVAILABLE")


def test_evidence_resources_hide_unheld_items(player):
    assert data(player.get("/evidence"))["items"] == []
    player.investigate("A01")
    [item] = data(player.get("/evidence"))["items"]
    assert item["evidence_id"] == "E01"
    assert item["kind"] == "DIGITAL"
    assert item["key_badge"] is False
    assert item["links"] == [] and item["known_conflicts"] == []
    assert item["source"] == {"kind": "SCENE", "id": "S01", "label": "档案室备用终端与现场核验单"}
    assert "is_key" not in item
    assert data(player.get("/evidence/E01")) == item
    unheld, unknown = player.get("/evidence/E05"), player.get("/evidence/E99")
    assert (unheld.status_code, code(unheld)) == (404, "EVIDENCE_NOT_FOUND")
    assert unheld.json()["error"]["message"] == unknown.json()["error"]["message"]


def test_npcs_are_the_four_interrogatable_people(player):
    items = data(player.get("/npcs"))["items"]
    assert [n["npc_id"] for n in items] == ["NPC01", "NPC02", "NPC03", "NPC04"]
    for npc in items:
        assert npc["is_contactable"] is True
        assert npc["admission_progress"] == "NONE"
        assert npc["fixed_statement"] is None
        assert npc["known_statements"] == []
        assert not {"pressure", "trust", "lies", "personality", "speech_style"} & set(npc)
    assert [t["topic_id"] for t in items[3]["topics"]] == ["Q04", "Q05"]
    assert data(player.get("/npcs/NPC04"))["name"] == "林澄"
    hidden = player.get("/npcs/VICTIM")
    assert (hidden.status_code, code(hidden)) == (404, "NPC_NOT_FOUND")


def test_known_statements_follow_their_speaker(player):
    player.investigate_all()
    player.talk("NPC04")
    player.ask_topic("Q05")
    npc04 = player.npc("NPC04")
    assert [k["information_ref"]["id"] for k in npc04["known_statements"]] == ["K10"]
    assert npc04["known_statements"][0]["source"] == {"kind": "NPC", "id": "NPC04", "label": "林澄"}
    assert player.npc("NPC01")["known_statements"] == []
    public = [k for k in player.load()["known_information"] if k["source"]["kind"] == "PUBLIC"]
    assert {k["information_ref"]["id"] for k in public} == {"K01", "K11"}


def test_relationship_graph_only_has_revealed_edges(player):
    graph = data(player.get("/relationships"))
    assert {n["character_id"] for n in graph["nodes"]} == {
        "NPC01",
        "NPC02",
        "NPC03",
        "NPC04",
        "VICTIM",
    }
    assert [e["relationship_id"] for e in graph["edges"]] == ["R01", "R02", "R03", "R04"]
    for action in ("A01", "A02", "A03"):
        player.investigate(action)
    edges = data(player.get("/relationships"))["edges"]
    assert [e["relationship_id"] for e in edges] == ["R01", "R02", "R03", "R04", "R05"]
    r05 = edges[-1]
    assert r05["source"] == {"kind": "EVIDENCE", "id": "E03", "label": "审计移交联与翻柜痕迹"}
    assert r05["discovered_at"] is not None
    assert edges[0]["discovered_at"] is None
    player.investigate_all(["A05", "A07", "A09"])
    edges = data(player.get("/relationships"))["edges"]
    r07 = next(e for e in edges if e["relationship_id"] == "R07")
    assert (r07["assertion_kind"], r07["credibility"]) == ("TESTIMONY", "UNVERIFIED")


def test_timeline_shows_known_items_in_stable_order_with_conflicts(player):
    timeline = data(player.get("/timeline"))
    assert timeline["origin_label"] == "案发当日 00:00"
    assert [i["timeline_event_id"] for i in timeline["items"]] == ["T08"]
    player.investigate_all()
    items = data(player.get("/timeline"))["items"]
    assert [i["timeline_event_id"] for i in items] == ["T01", "T02", "T03", "T04", "T06", "T08"]
    t04 = next(i for i in items if i["timeline_event_id"] == "T04")
    assert (t04["time_precision"], t04["time_start_minutes"], t04["time_end_minutes"]) == (
        "RANGE",
        1268,
        1278,
    )
    assert t04["known_conflicts"] == []
    player.talk("NPC03")
    player.ask_topic("Q03")
    player.talk("NPC01")
    for evidence in ("E01", "E03", "E02", "E08"):
        player.present(evidence)
    items = data(player.get("/timeline"))["items"]
    ids = [i["timeline_event_id"] for i in items]
    assert ids == ["T01", "T02", "T03", "T04", "T05", "T06", "T08", "T07"]
    t04 = next(i for i in items if i["timeline_event_id"] == "T04")
    assert t04["known_conflicts"] == [{"kind": "TIMELINE_EVENT", "id": "T05"}]
    t07 = items[-1]
    assert (t07["time_precision"], t07["time_start_minutes"], t07["time_end_minutes"]) == (
        "UNKNOWN",
        None,
        None,
    )
    assert t07["time_label"] == "门禁记录时段内，具体时间未知"


def test_accusation_options_and_empty_draft(player):
    options = data(player.get("/accusation-options"))
    assert [s["id"] for s in options["suspects"]] == ["NPC01", "NPC02", "NPC03", "NPC04"]
    assert options["process_constraints"] == {
        "min_steps": 1,
        "max_steps": 5,
        "allow_repeated_steps": False,
    }
    text = str(options)
    assert "is_correct" not in text and "points" not in text
    assert data(player.get("/accusation-draft")) == {"content": EMPTY_DRAFT}
    assert player.load()["accusation_draft"] == EMPTY_DRAFT
    assert player.load()["pending_conversations"] == []


def test_review_resources_are_closed_before_judgement(player):
    for suffix in ("/accusation", "/review"):
        response = player.get(suffix)
        assert (response.status_code, code(response)) == (409, "REVIEW_NOT_AVAILABLE")


def test_every_get_is_free_of_side_effects(player):
    player.investigate_all()
    player.talk("NPC01")
    player.present("E01")
    before = player.load()
    suffixes = [
        "",
        "/scenes",
        "/scenes/S03",
        "/evidence",
        "/evidence/E08",
        "/npcs",
        "/npcs/NPC01",
        "/npcs/NPC01/conversations",
        "/relationships",
        "/timeline",
        "/accusation-options",
        "/accusation-draft",
    ]
    for _ in range(2):
        for suffix in suffixes:
            assert player.get(suffix).status_code == 200, suffix
    assert player.client.get("/api/v1/sessions/current").status_code == 200
    assert player.load() == before
