import threading
import uuid

import pytest

from backend.application.sessions import Command, GameService

pytestmark = pytest.mark.integration


def run_together(*calls):
    barrier = threading.Barrier(len(calls))
    results = [None] * len(calls)

    def worker(index, call):
        barrier.wait()
        results[index] = call()

    threads = [threading.Thread(target=worker, args=pair) for pair in enumerate(calls)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results


def started(db):
    service = GameService(db)
    visitor = service.ensure_visitor(None).visitor_id
    created = service.create_session(
        visitor,
        Command(uuid.uuid4(), "POST", "/api/v1/sessions", {}),
        "case_001",
        "1-slice",
        None,
        False,
    )
    return service, visitor, uuid.UUID(created.body["session_id"])


def investigate(service, visitor, session_id, key, action_id):
    path = f"/api/v1/sessions/{session_id}/scenes/S01/investigations"
    command = Command(key, "POST", path, {"action_id": action_id}, 1)
    return lambda: service.investigate(visitor, session_id, command, "S01", action_id)


def test_two_new_keys_on_one_version_commit_only_once(db):
    service, visitor, session_id = started(db)
    results = run_together(
        investigate(service, visitor, session_id, uuid.uuid4(), "A01"),
        investigate(service, visitor, session_id, uuid.uuid4(), "A02"),
    )
    assert sorted(r.status_code for r in results) == [201, 409]
    conflict = next(r for r in results if r.status_code == 409)
    assert conflict.body["error"]["code"] == "STATE_VERSION_CONFLICT"
    view = service.session_view(visitor, session_id)
    assert view["session"]["state_version"] == 2
    assert len(view["evidence"]) == 1


def test_same_key_arriving_twice_is_applied_once(db):
    service, visitor, session_id = started(db)
    key = uuid.uuid4()
    results = run_together(
        investigate(service, visitor, session_id, key, "A01"),
        investigate(service, visitor, session_id, key, "A01"),
    )
    assert [r.status_code for r in results] == [201, 201]
    assert results[0].body == results[1].body
    assert service.session_view(visitor, session_id)["session"]["state_version"] == 2
