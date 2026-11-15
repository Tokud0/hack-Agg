import pytest
from fastapi.testclient import TestClient

from api.main import app
from llm import claude


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(claude, "_get_client", lambda: None)  # offline, deterministic
    with TestClient(app) as c:
        yield c


def test_state_has_both_runs_and_initial_plan(client):
    body = client.get("/api/state").json()
    assert set(body["runs"]) == {"baseline", "coordinator"}
    coord = body["runs"]["coordinator"]
    assert any(e["kind"] == "replan" for e in coord["log"])
    assert any(b["kind"] == "planned" for b in coord["gantt"])


def test_breakdown_event_replans_with_zero_violations(client):
    res = client.post("/api/events", json={"type": "breakdown", "tractor_id": "T1"})
    assert res.status_code == 200
    replan = res.json()["replan"]
    assert replan["accepted"] and replan["invariants"]["violations"] == []


def test_invalid_event_is_rejected(client):
    assert client.post("/api/events", json={"type": "breakdown", "tractor_id": "T9"}).status_code == 422
    assert client.post("/api/events", json={"type": "block_road", "a": "F1", "b": "F1"}).status_code == 422


def test_why_returns_facts_and_answer(client):
    res = client.get("/api/why/J05").json()
    assert res["facts"]["job_id"] == "J05"
    assert res["answer"] and res["source"] == "template"


def test_copilot_offline_understands_breakdown(client):
    res = client.post("/api/copilot", json={"message": "T1 broke down near F3"}).json()
    assert res["events"] == [{"type": "breakdown", "tractor_id": "T1"}]


def test_control_rejects_unknown_speed(client):
    assert client.post("/api/control", json={"action": "speed", "speed": 3}).status_code == 422
    assert client.post("/api/control", json={"action": "speed", "speed": 2}).json()["speed"] == 2


def test_export_contains_logs(client):
    body = client.get("/api/export").json()
    assert body["runs"]["coordinator"]["log"]


def test_explanation_template_mentions_unassignable_reason():
    diff = {"trigger": {"type": "breakdown", "tractor_id": "T1"}, "changes": [
        {"job_id": "J01", "before": "T1", "after": "unassignable", "reason": "deadline"},
        {"job_id": "J05", "before": "T1", "after": "T3", "reason": None}]}
    exp = claude.template_explanation(diff)
    assert "J05 T1→T3" in exp.summary and "deadline" in exp.summary
