from dataclasses import replace
from pathlib import Path

import pytest

from fleet.coordinator import plan
from fleet.engine import apply_event, metrics, run_to_end, start
from fleet.feasibility import StartContext, evaluate_queue
from fleet.invariants import check_plan
from fleet.models import JobStatus, Plan, TractorStatus
from fleet.replan import block_road, break_tractor, replan
from fleet.routing import build_network
from fleet.scenario import EventIn, ScenarioIn, load_scenario, random_scenario, to_world

SCENARIO_PATH = Path(__file__).resolve().parents[1] / "scenario.json"


@pytest.fixture
def scenario() -> ScenarioIn:
    return load_scenario(SCENARIO_PATH)


@pytest.fixture
def world(scenario):
    return to_world(scenario)


# --- routing -----------------------------------------------------------------


def test_blocked_road_forces_longer_detour(world):
    direct = build_network(world).distance("F1", "F2")
    detour = build_network(block_road(world, "F1", "F2"))
    assert detour.distance("F1", "F2") > direct
    assert len(detour.path("F1", "F2")) >= 2


# --- feasibility ---------------------------------------------------------------


def test_queue_rejects_wrong_implement(world):
    network = build_network(world)
    mower = world.tractors["T2"]
    ev = evaluate_queue(mower, StartContext("D", 0, mower.fuel), ("J01",), world.jobs, network)
    assert not ev.ok and "sprayer" in ev.reason


def test_queue_rejects_when_fuel_runs_out(world):
    network = build_network(world)
    t3 = world.tractors["T3"]
    no_deadlines = {jid: replace(job, deadline=99) for jid, job in world.jobs.items()}
    sprays = tuple(j for j, job in world.jobs.items() if job.type == "spray")
    ev = evaluate_queue(t3, StartContext("D", 0, t3.fuel), sprays, no_deadlines, network)
    assert not ev.ok and "fuel" in ev.reason


def test_queue_rejects_missed_deadline(world):
    network = build_network(world)
    t1 = world.tractors["T1"]
    late = StartContext("D", 10.0, t1.fuel)
    ev = evaluate_queue(t1, late, ("J02",), world.jobs, network)
    assert not ev.ok and "deadline" in ev.reason


# --- coordinator + invariants ------------------------------------------------


def test_initial_plan_passes_all_invariants(world):
    network = build_network(world)
    p = plan(world, network)
    assert check_plan(world, p, network).ok


def test_plan_is_deterministic(world):
    network = build_network(world)
    assert plan(world, network) == plan(world, network)


def test_invariant_checker_catches_duplicate_assignment(world):
    network = build_network(world)
    bad = Plan(queues={"T1": ("J01",), "T3": ("J01",), "T2": ()}, unassignable={})
    report = check_plan(world, bad, network)
    assert any("one_tractor_per_job" in v for v in report.violations)


def test_invariant_checker_catches_lost_job(world):
    network = build_network(world)
    report = check_plan(world, Plan(queues={"T1": (), "T2": (), "T3": ()}), network)
    assert any("every_open_job_accounted" in v for v in report.violations)


# --- re-plan on breakdown ----------------------------------------------------


def test_breakdown_releases_work_and_replans_safely(world):
    planned = replan(world).world
    broken = break_tractor(planned, "T1")
    result = replan(broken)
    assert result.accepted and result.report.ok
    assert result.plan.queues["T1"] == ()
    assert all(world.jobs[j].implement.value == "sprayer" for j in result.plan.queues["T3"])
    for jid in planned.tractors["T1"].queue:
        assert jid in result.plan.queues["T3"] or jid in result.plan.unassignable


def test_completed_work_is_never_reassigned(scenario):
    run = start(scenario, "coordinator", with_demo_events=False)
    while not any(j.status == JobStatus.DONE for j in run.world.jobs.values()):
        from fleet.engine import tick

        run = tick(run)
    done = {j.id for j in run.world.jobs.values() if j.status == JobStatus.DONE}
    run = apply_event(run, EventIn(at=run.world.time, type="breakdown", tractor_id="T1"))
    queued = {jid for t in run.world.tractors.values() for jid in t.queue}
    assert not (done & queued)
    assert all(run.world.jobs[j].status == JobStatus.DONE for j in done)


def test_interrupted_job_keeps_finished_share(scenario):
    from fleet.engine import tick

    run = start(scenario, "coordinator", with_demo_events=False)
    while not any(j.status == JobStatus.IN_PROGRESS and j.progress > 0.2 for j in run.world.jobs.values()):
        run = tick(run)
    job = next(j for j in run.world.jobs.values() if j.status == JobStatus.IN_PROGRESS and j.progress > 0.2)
    run = apply_event(run, EventIn(at=run.world.time, type="breakdown", tractor_id=job.tractor_id))
    assert run.world.jobs[job.id].remaining_hours == pytest.approx(job.remaining_hours)


# --- end to end --------------------------------------------------------------


def test_demo_coordinator_beats_baseline(scenario):
    ours = metrics(run_to_end(start(scenario, "coordinator")))
    base = metrics(run_to_end(start(scenario, "baseline")))
    assert ours["invariant_violations"] == 0
    assert ours["jobs_completed"] >= base["jobs_completed"]
    assert ours["priority1_completed"] >= base["priority1_completed"]


def test_demo_breakdown_flags_unreachable_job_with_reason(scenario):
    run = run_to_end(start(scenario, "coordinator"))
    assert run.world.tractors["T1"].status == TractorStatus.BROKEN
    flagged = [j for j in run.world.jobs.values() if j.status == JobStatus.UNASSIGNABLE]
    assert flagged and all(j.reason for j in flagged)


def test_executed_jobs_meet_their_deadlines(scenario):
    run = run_to_end(start(scenario, "coordinator"))
    for job in run.world.jobs.values():
        if job.status == JobStatus.DONE:
            assert job.completed_at <= job.deadline + 1e-6


@pytest.mark.parametrize("seed", range(15))
def test_random_scenarios_have_zero_violations(seed):
    run = run_to_end(start(random_scenario(seed), "coordinator"))
    m = metrics(run)
    assert m["invariant_violations"] == 0
    assert all(t.fuel >= -1e-6 for t in run.world.tractors.values())
    for job in run.world.jobs.values():
        if job.status == JobStatus.DONE:
            assert job.completed_at <= job.deadline + 1e-6


def test_scenario_rejects_unknown_field():
    with pytest.raises(ValueError):
        ScenarioIn.model_validate(
            {
                "depot": {"x": 0, "y": 0},
                "tractors": [{"id": "T1", "implement": "sprayer", "fuel_capacity": 10, "speed": 1,
                              "fuel_per_travel_hour": 1, "fuel_per_work_hour": 1}],
                "fields": [{"id": "F1", "x": 1, "y": 1}],
                "jobs": [{"id": "J1", "type": "spray", "field_id": "F9", "priority": 1, "deadline": 5, "work_hours": 1}],
            }
        )
