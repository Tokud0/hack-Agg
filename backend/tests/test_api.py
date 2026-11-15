import pytest
from fastapi.testclient import TestClient

from api.main import app
from llm import assistant as claude
from llm import provider


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(provider, "provider_name", lambda: None)  # offline, deterministic
    with TestClient(app) as c:
        yield c


def test_state_has_all_runs_and_initial_plan(client):
    body = client.get("/api/state").json()
    assert set(body["runs"]) == {"baseline", "edf", "coordinator"}
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


def test_add_job_replans_and_assigns(client):
    res = client.post("/api/jobs", json={"type": "mow", "field_id": "F5", "priority": 1, "deadline": 9, "work_hours": 1})
    assert res.status_code == 200
    job_id = res.json()["job_id"]
    jobs = {j["id"]: j for j in client.get("/api/state").json()["runs"]["coordinator"]["jobs"]}
    assert jobs[job_id]["status"] in ("assigned", "unassignable")


def test_add_job_rejects_unknown_field(client):
    res = client.post("/api/jobs", json={"type": "mow", "field_id": "F99", "priority": 1, "deadline": 9, "work_hours": 1})
    assert res.status_code == 422


def test_parse_jobs_offline(client):
    res = client.post("/api/jobs/parse", json={"text": "urgent: spray F2 and F6"}).json()
    assert [j["field_id"] for j in res["jobs"]] == ["F2", "F6"]
    assert all(j["type"] == "spray" and j["priority"] == 1 for j in res["jobs"])


def test_what_if_forecast_reports_lost_jobs(client):
    res = client.post("/api/whatif", json={"type": "breakdown", "tractor_id": "T3"}).json()
    assert res["facts"]["what_if"]["jobs_completed"] <= res["facts"]["current"]["jobs_completed"]
    assert res["answer"]


def test_upload_scenario_resets_session(client):
    from fleet.scenario import random_scenario

    body = random_scenario(3).model_dump(mode="json")
    assert client.post("/api/scenario", json=body).status_code == 200
    assert client.get("/api/state").json()["scenario"] == "random-3"


def test_strict_schema_requires_every_property():
    from llm.assistant import CopilotReply

    schema = provider.strict_schema(CopilotReply)
    event = schema["$defs"]["ProposedEvent"]
    assert set(event["required"]) == set(event["properties"]) and event["additionalProperties"] is False


def test_replan_log_entry_carries_the_orchestration_trace(client):
    res = client.post("/api/events", json={"type": "breakdown", "tractor_id": "T1", "source": "copilot"})
    replan = res.json()["replan"]
    trace = replan["trace"]
    assert set(trace) == {"sense", "plan", "verify", "dispatch"}
    assert "T1" not in trace["sense"]["tractors_available"]
    assert sum(c["is_winner"] for c in trace["plan"]["candidates"]) == 1
    assert trace["verify"]["accepted"] is True
    assert replan["diff"]["trigger"]["source"] == "copilot"


def test_fault_test_is_vetoed_without_changing_the_plan(client):
    before = client.get("/api/state").json()["runs"]["coordinator"]["tractors"]
    res = client.post("/api/orchestration/fault-test")
    assert res.status_code == 200
    body = res.json()
    assert body["accepted"] is False and body["violations"]
    assert client.get("/api/state").json()["runs"]["coordinator"]["tractors"] == before


def test_live_replans_carry_the_agent_conversation(client):
    client.post("/api/control", json={"action": "reset"})
    log = client.get("/api/state").json()["runs"]["coordinator"]["log"]
    messages = next(e for e in log if e["kind"] == "replan")["data"]["messages"]
    assert {m["phase"] for m in messages} >= {"situation", "auction", "approval"}
    assert any(m["kind"] == "claim" for m in messages)


def test_tractor_agent_answers_from_its_own_messages(client):
    res = client.post("/api/agents/T3/ask", json={"question": "What is your plan?"})
    assert res.status_code == 200
    assert res.json()["source"] == "template" and "planning round" in res.json()["answer"]


def test_asking_an_unknown_tractor_is_a_404(client):
    assert client.post("/api/agents/T9/ask", json={"question": "hi"}).status_code == 404
