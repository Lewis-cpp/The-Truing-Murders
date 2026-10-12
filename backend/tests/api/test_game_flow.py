import pytest
from conftest import make_client
from player import Player

pytestmark = [pytest.mark.api, pytest.mark.integration]


def test_full_slice_survives_backend_restart(client, migrated_url, monkeypatch):
    player = Player(client)
    created = player.start().json()
    assert created["result_state_version"] == 1
    assert created["data"]["session"]["phase"] == "INVESTIGATION"
    assert created["data"]["evidence"] == []

    gained = player.investigate("A01").json()
    assert gained["data"]["outcome"]["reason_code"] == "PROGRESS_UPDATED"
    assert [e["evidence_id"] for e in gained["data"]["outcome"]["new_evidence"]] == ["E01"]
    assert player.investigate("A02").status_code == 201
    assert player.investigate("A03").status_code == 201
    assert player.talk().status_code == 201
    broken = player.present("E01").json()["data"]
    assert broken["outcome"]["reason_code"] == "LIE_BROKEN"
    admitted = player.present("E03").json()["data"]
    assert admitted["outcome"]["reason_code"] == "ADMISSION_RECORDED"
    assert admitted["outcome"]["disclosed_information"][0]["credibility"] == "UNVERIFIED"
    before_restart = player.load()

    # A new app instance has a new engine and empty caches; only the database remains.
    client.__exit__(None, None, None)
    with make_client(monkeypatch, migrated_url) as restarted:
        restarted.cookies = client.cookies
        current = restarted.get("/api/v1/sessions/current").json()
        assert current["session"] == before_restart
        player.client = restarted
        assert player.write("DELETE", player.path("/interrogation")).status_code == 200
        assert player.load()["session"]["phase"] == "DEEP_INVESTIGATION"
        assert player.accuse().status_code == 201
        verdict = player.submit().json()
        assert verdict["data"]["verdict"]["category"] == "CORRECT"
        assert verdict["data"]["verdict"]["score"] == "100.00"
        review = restarted.get(player.path("/review")).json()["data"]
        assert review["missed_evidence"] == []
        assert "B17" in review["truth"]["explanation"]
        assert player.write("PUT", player.path("/review-completion"), {}).status_code == 201
        assert player.load()["session"]["phase"] == "FINISHED"
