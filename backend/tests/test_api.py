import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from llm import assistant as claude
from llm import provider

DEMO_SCENARIO = Path(__file__).resolve().parents[1] / "scenario.json"


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
    assert set(trace) == {"sense", "agronomy", "navigate", "plan", "verify", "dispatch"}
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


def test_scheduled_fault_fires_on_the_clock_and_the_fleet_recovers_without_a_click(client):
    client.post("/api/control", json={"action": "reset"})
    res = client.post("/api/events/schedule", json={"tractor_id": "T1", "delay_hours": 0.5})
    assert res.status_code == 200 and res.json()["at"] == 0.5
    assert client.get("/api/state").json()["scheduled_faults"] == [{"tractor_id": "T1", "at": 0.5}]

    from api.main import session
    session().running = True
    for _ in range(60):  # 6 real seconds at 1x = 0.9 simulated hours; no event is posted
        session().advance(0.1)

    state = client.get("/api/state").json()
    coord = state["runs"]["coordinator"]
    assert state["scheduled_faults"] == []
    assert next(t for t in coord["tractors"] if t["id"] == "T1")["status"] == "broken"
    replans = [e for e in coord["log"] if e["kind"] == "replan"]
    assert replans[-1]["data"]["diff"]["trigger"]["source"] == "telemetry"
    assert replans[-1]["data"]["accepted"] and replans[-1]["data"]["invariants"]["violations"] == []
    assert all(not t["queue"] for t in coord["tractors"] if t["id"] == "T1")


def test_scheduling_a_fault_for_an_unknown_tractor_is_rejected(client):
    assert client.post("/api/events/schedule", json={"tractor_id": "T9", "delay_hours": 1}).status_code == 422


def test_tractor_agent_can_be_asked_about_an_older_round(client):
    client.post("/api/control", json={"action": "reset"})
    client.post("/api/events", json={"type": "breakdown", "tractor_id": "T1"})
    log = client.get("/api/state").json()["runs"]["coordinator"]["log"]
    first = next(e["index"] for e in log if e["kind"] == "replan")
    res = client.post("/api/agents/T1/ask", json={"question": "What did you take?", "replan_index": first})
    assert res.status_code == 200 and "is mine" in res.json()["answer"]
    assert client.post("/api/agents/T1/ask", json={"question": "x", "replan_index": 0}).status_code == 404


def test_random_scenario_can_be_fetched_then_started(client):
    scenario = client.get("/api/scenario/random", params={"seed": 5}).json()
    assert scenario["name"] == "Random shift #5"
    before = client.get("/api/state").json()["session_id"]
    assert client.post("/api/scenario", json=scenario).status_code == 200
    state = client.get("/api/state").json()
    assert state["scenario"] == "Random shift #5" and state["session_id"] != before
    assert client.get("/api/scenario").json()["fields"] == scenario["fields"]


def test_describing_a_scenario_offline_reads_the_counts(client):
    res = client.post("/api/scenario/describe", json={"text": "2 tractors, 4 fields and 6 jobs please"})
    body = res.json()
    assert res.status_code == 200 and body["source"] == "template"
    scenario = body["scenario"]
    assert (len(scenario["tractors"]), len(scenario["fields"])) == (2, 4)
    # The seed is random and the result is then made finishable, which may drop a job that cannot fit.
    assert 1 <= len(scenario["jobs"]) <= 6 and len(scenario["jobs"]) + sum("removed" in c for c in body["changes"]) == 6


def test_invalid_scenario_is_rejected(client):
    assert client.post("/api/scenario", json={"name": "x", "depot": {"x": 5, "y": 0}, "tractors": [], "fields": [], "jobs": []}).status_code == 422


def test_random_shift_arms_surprises_that_fire_without_a_click(client):
    scenario = client.get("/api/scenario/random", params={"seed": 3, "trouble": "high"}).json()
    assert scenario["auto_events"] and scenario["demo_events"]
    client.post("/api/scenario", json=scenario)
    state = client.get("/api/state").json()
    assert state["surprises_left"] == len(scenario["demo_events"]) and state["scheduled_faults"] == []

    from api.main import session
    session().running, session().speed = True, 8.0
    for _ in range(80):  # 8 real seconds at 8x = 9.6 simulated hours
        session().advance(0.1)
    state = client.get("/api/state").json()
    replans = [e for e in state["runs"]["coordinator"]["log"] if e["kind"] == "replan"]
    assert state["surprises_left"] == 0
    assert {r["data"]["diff"]["trigger"].get("source") for r in replans[1:]} == {"surprise"}
    assert all(r["data"]["invariants"]["violations"] == [] for r in replans)


def test_check_reports_impossible_jobs_and_offers_a_fix(client):
    scenario = client.get("/api/scenario/random", params={"seed": 4}).json()
    assert client.post("/api/scenario/check", json=scenario).json()["impossible"] == {}
    scenario["jobs"][0]["deadline"] = 0.3
    body = client.post("/api/scenario/check", json=scenario).json()
    job_id = scenario["jobs"][0]["id"]
    assert job_id in body["impossible"] and body["fixed"] and any(c.startswith(job_id) for c in body["changes"])


def test_uploaded_scenario_can_ask_for_generated_surprises(client):
    scenario = client.get("/api/scenario/random", params={"seed": 6}).json()
    client.post("/api/scenario", json={**scenario, "demo_events": [], "auto_events": True, "trouble": "high"})
    assert client.get("/api/state").json()["surprises_left"] >= 4
    client.post("/api/scenario", json={**scenario, "demo_events": [], "auto_events": True, "trouble": "low"})
    assert 1 <= client.get("/api/state").json()["surprises_left"] <= 4
    client.post("/api/scenario", json={**scenario, "auto_events": False})
    assert client.get("/api/state").json()["surprises_left"] == 0


def test_scenario_with_an_event_for_a_missing_tractor_is_rejected(client):
    scenario = client.get("/api/scenario/random", params={"seed": 8}).json()
    scenario["demo_events"] = [{"at": 1.0, "type": "breakdown", "tractor_id": "T9"}]
    assert client.post("/api/scenario", json=scenario).status_code == 422


def test_briefing_reports_progress_and_what_needs_attention(client):
    client.post("/api/scenario", json=json.loads(DEMO_SCENARIO.read_text()))
    client.post("/api/events", json={"type": "breakdown", "tractor_id": "T1"})
    body = client.get("/api/briefing").json()
    assert body["source"] == "template" and body["jobs"]["total"] == 10
    kinds = {a["kind"] for a in body["attention"]}
    assert "broken" in kinds and any(a["id"] == "T1" for a in body["attention"])
    assert body["events"] and "need" in body["headline"]


def test_state_gives_every_planned_job_its_spare_time(client):
    jobs = client.get("/api/state").json()["runs"]["coordinator"]["jobs"]
    planned = [j for j in jobs if j["status"] in ("assigned", "in_progress")]
    assert planned and all(j["slack"] is not None and j["projected_finish"] is not None for j in planned)


def test_weather_event_holds_spraying_and_the_agronomy_agent_says_so(client):
    client.post("/api/scenario", json=json.loads(DEMO_SCENARIO.read_text()))
    res = client.post("/api/events", json={"type": "weather", "job_type": "spray", "hours": 2})
    assert res.status_code == 200
    replan = res.json()["replan"]
    assert replan["accepted"] and replan["invariants"]["violations"] == []
    assert replan["trace"]["agronomy"]["holds"] == [{"job_type": "spray", "until": 2.0}]
    alert = replan["messages"][0]
    assert alert["sender"] == "agronomy_agent" and "on hold until 08:00" in alert["text"]
    state = client.get("/api/state").json()
    assert state["weather_holds"] == [{"job_type": "spray", "until": 2.0}]
    spray = [j for j in state["runs"]["coordinator"]["jobs"] if j["type"] == "spray"]
    assert all(j["not_before"] == 2.0 for j in spray)
    assert all(j["projected_finish"] is None or j["projected_finish"] >= 2.0 + j["work_hours"] - 1e-6 for j in spray)


def test_weather_event_without_a_duration_is_rejected(client):
    assert client.post("/api/events", json={"type": "weather", "job_type": "spray"}).status_code == 422


def test_random_shift_can_be_asked_for_no_trouble_at_all(client):
    scenario = client.get("/api/scenario/random", params={"seed": 9, "trouble": "none"}).json()
    assert scenario["demo_events"] == [] and scenario["auto_events"] is False
