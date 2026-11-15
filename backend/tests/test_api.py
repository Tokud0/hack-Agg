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
    assert set(trace) == {"sense", "agronomy", "navigate", "plan", "verify", "recovery", "dispatch"}
    assert 0 < trace["recovery"]["event_to_plan_ms"] < 2000
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


def test_copilot_state_carries_ready_made_counts_and_durations(client):
    client.post("/api/scenario", json=json.loads(DEMO_SCENARIO.read_text()))
    from api.main import session
    state = session().copilot_state()
    assert state["shift"] == {"started_at": "06:00", "is_finished": False, "hours_elapsed": 0.0, "total_duration_hours": None, "ended_at": None}
    assert state["totals"]["jobs"] == 10 and state["totals"]["by_type"]["spray"]["total"] == 7 and state["totals"]["by_type"]["mow"]["total"] == 3

    session().running, session().speed = True, 8.0
    for _ in range(150):
        session().advance(0.1)
    done = session().copilot_state()
    totals = done["totals"]
    assert done["shift"]["is_finished"] and done["shift"]["total_duration_hours"] == done["shift"]["hours_elapsed"] > 5
    assert totals["done"] + totals["cannot_be_done"] == totals["jobs"] and totals["in_progress"] == totals["waiting"] == 0
    assert sum(t["done"] for t in totals["by_type"].values()) == totals["done"]
    assert all(j["finished_at"] for j in done["jobs"].values() if j["status"] == "done")


def test_offline_copilot_answers_a_question_with_the_facts(client):
    res = client.post("/api/copilot", json={"message": "how long did it take to do all the work?"})
    assert res.status_code == 200 and "jobs done on time" in res.json()["reply"] and res.json()["events"] == []


def test_rate_limited_calls_move_to_the_second_key_then_the_backup_model(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "first")
    monkeypatch.setenv("GROQ_API_KEY_2", "second")
    calls = []

    def fake_once(model, api_key, system, user, schema):
        calls.append((model, api_key))
        is_last = (model, api_key) == (provider.groq_backup_model(), "second")
        return (schema(headline="ok", summary="ok"), False) if is_last else (None, True)

    monkeypatch.setattr(provider, "_groq_once", fake_once)
    result = provider._groq("system", "user", claude.Briefing)
    main, backup = provider.groq_model(), provider.groq_backup_model()
    assert calls == [(main, "first"), (main, "second"), (backup, "first"), (backup, "second")] and result.headline == "ok"


def test_second_key_answers_when_the_first_is_rate_limited(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "first")
    monkeypatch.setenv("GROQ_API_KEY_2", "second")
    calls = []

    def fake_once(model, api_key, system, user, schema):
        calls.append(api_key)
        return (None, True) if api_key == "first" else (schema(headline="ok", summary="ok"), False)

    monkeypatch.setattr(provider, "_groq_once", fake_once)
    assert provider._groq("system", "user", claude.Briefing).headline == "ok" and calls == ["first", "second"]


def test_nothing_else_is_tried_for_failures_other_than_a_rate_limit(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "first")
    monkeypatch.setenv("GROQ_API_KEY_2", "second")
    calls = []
    monkeypatch.setattr(provider, "_groq_once", lambda model, *rest: (calls.append(model), (None, False))[1])
    assert provider._groq("system", "user", claude.Briefing) is None and len(calls) == 1


# --- Incident Response Agent: real tool calls ---------------------------------


def _incident_session():
    from api.session import Session
    from fleet.scenario import EventIn
    session = Session.create()
    session.apply_event(EventIn(at=0, type="breakdown", tractor_id="T1"))
    index = max(i for i, e in enumerate(session.runs["coordinator"].log) if e.kind == "replan")
    return session, index


def test_every_event_gets_a_review_even_with_no_model(client):
    session, index = _incident_session()
    record = session.incident_reviews[index]
    assert record["source"] == "template" and record["review"]["severity"] in ("low", "medium", "high")
    assert record["notes"] == ["automatic check without the LLM; the agent investigates on request"]
    assert [c["tool"] for c in record["calls"]] == ["get_incident", "evaluate_deadline_risk", "forecast_rest_of_shift", "file_incident_review"]
    assert all(c["ok"] and c["chosen_by"] == "script" for c in record["calls"])
    assert 0 not in session.incident_reviews  # the opening plan is not an incident


def test_model_chosen_tool_calls_are_run_validated_and_recorded(client, monkeypatch):
    from api.incident import review_incident
    session, index = _incident_session()
    turns = iter([
        [("a", "get_incident", "{}"), ("b", "get_job_detail", '{"job_id": "J05"}')],
        [("c", "get_job_detail", '{"job_id": "J99"}'), ("d", "launch_tractor", "{}")],
        [("e", "file_incident_review", '{"severity": "medium", "finding": "T1 is out; J05 moved.", "recommendation": "No action needed."}')],
    ])

    def fake_chat(messages, tools):
        return {"content": "", "tool_calls": [{"id": i, "type": "function", "function": {"name": n, "arguments": a}} for i, n, a in next(turns)]}

    monkeypatch.setattr(provider, "provider_name", lambda: "groq")
    monkeypatch.setattr(provider, "chat_with_tools", fake_chat)
    record = review_incident(session, index)
    calls = {(c["tool"], c["ok"]) for c in record["calls"]}
    assert record["source"] == "groq" and record["review"]["finding"] == "T1 is out; J05 moved."
    assert ("get_job_detail", True) in calls and ("get_job_detail", False) in calls  # unknown job is refused with a reason
    assert ("launch_tractor", False) in calls  # a tool that is not registered is never run
    assert all(c["chosen_by"] == "model" for c in record["calls"])


def test_review_falls_back_when_the_model_never_concludes(client, monkeypatch):
    from api.incident import review_incident
    session, index = _incident_session()
    monkeypatch.setattr(provider, "provider_name", lambda: "groq")
    monkeypatch.setattr(provider, "chat_with_tools", lambda messages, tools: None)
    record = review_incident(session, index)
    assert record["source"] == "template" and record["review"] and record["notes"] == ["no model answered"]


def test_incident_tools_never_change_the_fleet(client):
    from api.incident import build_registry
    from llm.tool_agent import call_tool
    session, index = _incident_session()
    before = session.runs["coordinator"].world
    registry = build_registry(session, index)
    for name in ("get_incident", "get_fleet_snapshot", "evaluate_deadline_risk", "forecast_rest_of_shift"):
        assert call_tool(registry, name, {}).ok
    assert session.runs["coordinator"].world == before


def test_agent_does_not_call_a_model_by_itself_but_does_on_request(client, monkeypatch):
    asked = []
    monkeypatch.setattr(provider, "provider_name", lambda: "groq")
    monkeypatch.setattr(provider, "chat_with_tools", lambda messages, tools: asked.append(1))
    monkeypatch.setattr(provider, "structured", lambda *args: (None, "template"))
    monkeypatch.delenv("INCIDENT_AGENT_AUTO", raising=False)
    client.post("/api/scenario", json=json.loads(DEMO_SCENARIO.read_text()))
    client.post("/api/events", json={"type": "breakdown", "tractor_id": "T1"})
    reviews = client.get("/api/state").json()["incident_reviews"]
    assert asked == [] and len(reviews) == 1  # the automatic check ran, the model was not touched
    index = next(iter(reviews))
    res = client.post(f"/api/incidents/{index}/investigate")
    assert res.status_code == 200 and asked  # asked for: now the model is consulted
    assert client.post("/api/incidents/0/investigate").status_code == 404


# --- scenario from a description keeps what was asked for ---------------------


def test_described_scenario_keeps_every_field_and_arms_the_described_breakdown(client, monkeypatch):
    from fleet.scenario import EventDraft, FieldDraft, JobDraftIn, ScenarioDraft, TractorDraft
    draft = ScenarioDraft(
        name="Ten fields",
        tractors=[TractorDraft(implement="sprayer"), TractorDraft(implement="sprayer"), TractorDraft(implement="mower")],
        fields=[FieldDraft(x=x, y=y) for x in (1, 3, 5, 7, 9) for y in (3, 7)],
        jobs=[JobDraftIn(type="spray", field_number=n, priority=2, deadline_hours=8, work_hours=1) for n in range(1, 7)],
        events=[EventDraft(type="breakdown", at_hours=2.0, tractor_number=1), EventDraft(type="breakdown", at_hours=3.0, tractor_number=9)],
    )
    monkeypatch.setattr(claude, "_ask", lambda system, user, schema: (draft, "groq"))
    body = client.post("/api/scenario/describe", json={"text": "3 tractors, 10 fields, one breakdown"}).json()
    scenario = body["scenario"]
    assert len(scenario["fields"]) == 10 and len(scenario["tractors"]) == 3
    assert {j["field_id"] for j in scenario["jobs"]} == {f["id"] for f in scenario["fields"]}  # no field is left without work
    assert [(e["type"], e["tractor_id"], e["at"]) for e in scenario["demo_events"]] == [("breakdown", "T1", 2.0)]
    assert scenario["auto_events"] is True
    assert "Event at 08:00: T1 breaks down" in body["changes"] and any("added so every field has work" in c for c in body["changes"])
    assert client.post("/api/scenario", json=scenario).status_code == 200
    assert client.get("/api/state").json()["surprises_left"] == 1


def test_described_scenario_offline_keeps_the_field_count_and_a_mentioned_breakdown(client):
    body = client.post("/api/scenario/describe", json={"text": "3 tractors, 10 fields, 12 jobs and one breakdown"}).json()
    scenario = body["scenario"]
    assert body["source"] == "template" and len(scenario["fields"]) == 10 and len(scenario["tractors"]) == 3
    assert [e["type"] for e in scenario["demo_events"]] == ["breakdown"]


def test_impossible_job_in_a_described_scenario_is_kept_and_reported():
    from fleet.generate import make_feasible
    from fleet.scenario import random_live_scenario
    scenario = random_live_scenario(1)
    heavy = scenario.model_copy(update={"jobs": [scenario.jobs[0].model_copy(update={"work_hours": 40.0}), *scenario.jobs[1:]]})
    kept, notes = make_feasible(heavy, remove_impossible=False)
    assert len(kept.jobs) == len(heavy.jobs) and any("kept, but it cannot be done" in n for n in notes)
    removed, _ = make_feasible(heavy)
    assert heavy.jobs[0].id not in {j.id for j in removed.jobs}  # the default still drops what cannot be done
