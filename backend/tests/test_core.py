from dataclasses import replace
from pathlib import Path

import pytest

from fleet.coordinator import plan
from fleet.engine import apply_event, metrics, run_to_end, start, tick
from fleet.feasibility import StartContext, evaluate_queue
from fleet.generate import impossible_at_start, make_feasible, random_shift
from fleet.invariants import check_plan
from fleet.models import JobStatus, Plan, TractorStatus
from fleet.risk import at_risk, outlook
from fleet.replan import block_road, break_tractor, current_plan, fault_test, on_closed_stretch, replan, reroute_in_transit
from fleet.agents import Recorder, transcript
from fleet.routing import build_network
from fleet.scenario import (
    EventIn, FieldDraft, JobDraftIn, ScenarioDraft, ScenarioIn, TractorDraft, load_scenario, random_live_scenario,
    random_scenario, scenario_from_draft, to_world,
)

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
    ev = evaluate_queue(mower, StartContext("D", 0, mower.fuel), ("J01",), world, network)
    assert not ev.ok and "sprayer" in ev.reason


def _no_deadlines(world):
    return replace(world, jobs={jid: replace(job, deadline=99) for jid, job in world.jobs.items()})


def test_queue_rejects_when_fuel_runs_out_without_refuelling(world):
    network = build_network(world)
    t3 = world.tractors["T3"]
    sprays = tuple(j for j, job in world.jobs.items() if job.type == "spray")
    no_refuel = replace(_no_deadlines(world), refuel_hours=None)
    ev = evaluate_queue(t3, StartContext("D", 0, t3.fuel), sprays, no_refuel, network)
    assert not ev.ok and "fuel" in ev.reason


def test_queue_inserts_depot_refuel_when_tank_runs_low(world):
    network = build_network(world)
    t3 = world.tractors["T3"]
    sprays = tuple(j for j, job in world.jobs.items() if job.type == "spray")
    ev = evaluate_queue(t3, StartContext("D", 0, t3.fuel), sprays, _no_deadlines(world), network)
    assert ev.ok and ev.refuel_stops
    assert ev.fuel_left >= 0


def test_refuel_stop_costs_time(world):
    network = build_network(world)
    t3 = world.tractors["T3"]
    sprays = tuple(j for j, job in world.jobs.items() if job.type == "spray")
    relaxed = _no_deadlines(world)
    slow = evaluate_queue(t3, StartContext("D", 0, t3.fuel), sprays, replace(relaxed, refuel_hours=1.0), network)
    fast = evaluate_queue(t3, StartContext("D", 0, t3.fuel), sprays, replace(relaxed, refuel_hours=0.1), network)
    assert slow.end_time > fast.end_time


def test_job_larger_than_full_tank_is_rejected(world):
    network = build_network(world)
    t3 = world.tractors["T3"]
    huge = replace(world, jobs={**world.jobs, "J01": replace(world.jobs["J01"], remaining_hours=20, deadline=99)})
    ev = evaluate_queue(t3, StartContext("D", 0, t3.fuel), ("J01",), huge, network)
    assert not ev.ok and "full tank" in ev.reason


def test_queue_rejects_missed_deadline(world):
    network = build_network(world)
    t1 = world.tractors["T1"]
    late = StartContext("D", 10.0, t1.fuel)
    ev = evaluate_queue(t1, late, ("J02",), world, network)
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


def test_simulated_refuel_matches_plan(world):
    """A tractor that must refuel follows the planned depot stop and still meets the deadline."""
    from fleet.engine import tick

    low = replace(world, tractors={**world.tractors, "T3": replace(world.tractors["T3"], fuel=10)})
    scenario_run = start(load_scenario(SCENARIO_PATH), "coordinator", with_demo_events=False)
    run = replace(scenario_run, world=replace(low, time=0.0))
    run = replan_run = apply_event(run, EventIn(at=0, type="change_priority", job_id="J02", priority=1))
    assert replan_run.world.tractors["T3"].queue or replan_run.world.tractors["T3"].current_job
    for _ in range(400):
        run = tick(run)
    t3 = run.world.tractors["T3"]
    assert t3.refuels >= 1 and t3.fuel >= -1e-6
    for job in run.world.jobs.values():
        if job.status == JobStatus.DONE:
            assert job.completed_at <= job.deadline + 1e-6


# --- orchestration trace -----------------------------------------------------


def test_replan_records_every_candidate_and_exactly_one_winner(world):
    result = replan(world)
    assert len(result.candidates) >= 4
    winners = [c for c in result.candidates if c.is_winner]
    assert len(winners) == 1
    assert winners[0].score == max(c.score for c in result.candidates if c.score is not None)


def test_fault_test_is_rejected_and_leaves_the_world_untouched(world):
    planned = replan(world).world
    result = fault_test(planned)
    assert result is not None and not result.report.ok
    assert any("one_tractor_per_job" in v for v in result.report.violations)
    assert current_plan(planned) == current_plan(replan(world).world)


def test_fault_test_has_nothing_to_corrupt_before_any_plan(world):
    assert fault_test(world) is None


# --- agent conversation ------------------------------------------------------


def _replay_queues(messages) -> dict[str, tuple[str, ...]]:
    """Rebuild the plan from the conversation alone: claims, then trades."""
    queues: dict[str, tuple[str, ...]] = {}
    for m in messages:
        if m.kind == "claim":
            queues = {**queues, m.sender: tuple(m.data["queue"])}
        elif "queues" in m.data:
            queues = {tid: tuple(q) for tid, q in m.data["queues"].items()}
    return queues


def _conversation(world, trigger=None, released=None):
    network = build_network(world)
    result = replan(world, network, Recorder)
    return result, transcript(world, network, trigger or {"type": "initial_plan"}, released or {}, result)


def test_conversation_alone_reproduces_the_plan(world):
    result, messages = _conversation(world)
    replayed = _replay_queues(messages)
    assert {tid: q for tid, q in result.plan.queues.items() if q} == {tid: q for tid, q in replayed.items() if q}


def test_every_award_goes_to_the_lowest_bid(world):
    _, messages = _conversation(world)
    awards = [m for m in messages if m.kind == "award"]
    assert awards
    for award in awards:
        bids = [m for m in messages if m.kind == "bid" and m.topic == award.topic]
        best = min(bids, key=lambda m: m.data["value"])
        assert best.sender == award.to and best.data["is_winner"]


def test_every_working_tractor_answers_every_announcement(world):
    _, messages = _conversation(world)
    for announce in (m for m in messages if m.kind == "announce"):
        answered = {m.sender for m in messages if m.topic == announce.topic and m.kind in ("bid", "decline")}
        assert answered == set(world.tractors)


def test_broken_tractor_announces_release_and_stays_out_of_the_auction(world):
    planned = replan(world).world
    released = {jid: "T1" for jid in planned.tractors["T1"].queue}
    broken = break_tractor(planned, "T1")
    result, messages = _conversation(broken, {"type": "breakdown", "tractor_id": "T1"}, released)
    assert messages[0].sender == "T1" and messages[0].kind == "alert"
    assert not [m for m in messages if m.sender == "T1" and m.kind in ("bid", "decline", "ack")]
    assert _replay_queues(messages).get("T3", ()) == result.plan.queues["T3"]
    closing = [m.kind for m in messages if m.kind != "risk"]  # deadline warnings, if any, come after the confirmations
    assert closing[-1] == "ack" and any(m.kind == "verdict" and m.data["accepted"] for m in messages)


def test_navigation_agent_reports_the_detour_and_routes_the_winners(world):
    planned = replan(world).world
    blocked = block_road(planned, "F4", "F6")
    _, messages = _conversation(blocked, {"type": "block_road", "a": "F4", "b": "F6"})
    alert = messages[0]
    assert alert.sender == "navigation_agent" and "Detour: F4" in alert.text
    awards = [m for m in messages if m.kind == "award"]
    routes = [m for m in messages if m.kind == "route"]
    assert len(routes) == len(awards) and all(m.sender == "navigation_agent" for m in routes)


# --- safety checks against corrupt state -------------------------------------


def _working_world(world):
    """The demo shift a little after 07:00, with tractors on their first jobs."""
    run = start(load_scenario(SCENARIO_PATH), "coordinator", with_demo_events=False)
    while run.world.time < 1.2:
        run = tick(run, 0.05)
    return run.world


def test_two_tractors_on_the_same_current_job_are_vetoed(world):
    live = _working_world(world)
    job_id = live.tractors["T1"].current_job
    assert job_id
    corrupt = replace(live, tractors={**live.tractors, "T3": replace(live.tractors["T3"], current_job=job_id)})
    report = check_plan(corrupt, current_plan(corrupt), build_network(corrupt))
    assert any(v.startswith("one_tractor_per_job") and "2 tractors" in v for v in report.violations)


def test_current_job_with_the_wrong_implement_is_vetoed(world):
    live = _working_world(world)
    mow_job = live.tractors["T2"].current_job
    assert mow_job
    corrupt = replace(live, tractors={**live.tractors, "T2": replace(live.tractors["T2"], current_job=None, queue=()),
                                      "T1": replace(live.tractors["T1"], current_job=mow_job)})
    report = check_plan(corrupt, current_plan(corrupt), build_network(corrupt))
    assert any("carries a sprayer" in v for v in report.violations)


def test_current_job_without_enough_fuel_is_vetoed(world):
    live = _working_world(world)
    corrupt = replace(live, tractors={**live.tractors, "T1": replace(live.tractors["T1"], fuel=0.5)})
    report = check_plan(corrupt, current_plan(corrupt), build_network(corrupt))
    assert any("runs out of fuel" in v for v in report.violations)


def test_current_job_past_its_deadline_is_reported_but_not_vetoed(world):
    live = _working_world(world)
    job_id = live.tractors["T1"].current_job
    late = replace(live, jobs={**live.jobs, job_id: replace(live.jobs[job_id], deadline=live.time)})
    report = check_plan(late, current_plan(late), build_network(late))
    assert report.ok and any(job_id in w for w in report.warnings)


def test_healthy_shift_has_no_violations_or_warnings(world):
    live = _working_world(world)
    report = check_plan(live, current_plan(live), build_network(live))
    assert report.ok and not report.warnings


# --- road closing under a driving tractor ------------------------------------


def _driving(world, tractor_id, node, path, x, y):
    return replace(world, tractors={**world.tractors, tractor_id: replace(
        world.tractors[tractor_id], status=TractorStatus.TRAVELING, node=node, path=path, x=x, y=y)})


def test_tractor_already_on_the_closed_road_finishes_that_stretch(world):
    (ax, ay), (bx, by) = world.node_position("F1"), world.node_position("F4")
    moving = _driving(world, "T1", "F1", ("F4",), (ax + bx) / 2, (ay + by) / 2)
    assert on_closed_stretch(moving, "T1", "F4", "F1")
    closed = block_road(moving, "F1", "F4")
    assert reroute_in_transit(closed, build_network(closed)).tractors["T1"].path == ("F4",)


def test_tractor_that_has_not_left_its_node_is_routed_around_the_closed_road(world):
    ax, ay = world.node_position("F1")
    waiting = _driving(world, "T1", "F1", ("F4",), ax, ay)
    assert not on_closed_stretch(waiting, "T1", "F1", "F4")
    closed = block_road(waiting, "F1", "F4")
    network = build_network(closed)
    path = reroute_in_transit(closed, network).tractors["T1"].path
    assert path == network.path("F1", "F4") and len(path) > 1


def test_later_legs_of_a_route_avoid_a_road_that_closes_ahead(world):
    (ax, ay), (bx, by) = world.node_position("F1"), world.node_position("F4")
    moving = _driving(world, "T1", "F1", ("F4", "F6"), (ax + bx) / 2, (ay + by) / 2)
    closed = block_road(moving, "F4", "F6")
    network = build_network(closed)
    path = reroute_in_transit(closed, network).tractors["T1"].path
    assert path[0] == "F4" and path[-1] == "F6" and path == ("F4", *network.path("F4", "F6"))
    assert all(frozenset(leg) != frozenset(("F4", "F6")) for leg in zip(path, path[1:]))


# --- live scenarios ----------------------------------------------------------


@pytest.mark.parametrize("seed", range(25))
def test_random_live_scenario_is_valid_spread_out_and_fully_staffed(seed):
    scenario = random_live_scenario(seed)
    spots = [(f.x, f.y) for f in scenario.fields]
    assert len(set(spots)) == len(spots) and (scenario.depot.x, scenario.depot.y) not in spots
    implements = {t.implement.value for t in scenario.tractors}
    assert all({"spray": "sprayer", "mow": "mower"}[j.type] in implements for j in scenario.jobs)
    run = run_to_end(start(scenario, "coordinator", with_demo_events=False))
    assert metrics(run)["invariant_violations"] == 0


def test_random_live_scenarios_differ_between_seeds():
    assert random_live_scenario(1) != random_live_scenario(2)
    assert random_live_scenario(7) == random_live_scenario(7)


def test_draft_is_clamped_and_overlapping_fields_are_moved_apart():
    draft = ScenarioDraft(
        name="  ",
        tractors=[TractorDraft(implement="sprayer", fuel_capacity=9999)],
        fields=[FieldDraft(x=3, y=3), FieldDraft(x=3, y=3), FieldDraft(x=50, y=-4)],
        jobs=[JobDraftIn(type="spray", field_number=1, priority=9, deadline_hours=0.1, work_hours=2),
              JobDraftIn(type="spray", field_number=99, priority=1, deadline_hours=5, work_hours=1)],
    )
    scenario = scenario_from_draft(draft)
    assert scenario.name == "Custom shift" and scenario.tractors[0].fuel_capacity == 200
    assert len({(f.x, f.y) for f in scenario.fields}) == 3 and all(0 <= f.x <= 10 and 1 <= f.y <= 10 for f in scenario.fields)
    assert [j.field_id for j in scenario.jobs] == ["F1"]  # the job on a missing field is dropped
    assert scenario.jobs[0].priority == 3 and scenario.jobs[0].deadline == 2.5


def test_draft_with_nothing_usable_is_rejected():
    with pytest.raises(ValueError):
        scenario_from_draft(ScenarioDraft(name="x", tractors=[], fields=[], jobs=[]))


# --- generated shifts: feasible at the start, then surprised ------------------


@pytest.mark.parametrize("seed", range(30))
def test_random_shift_can_be_finished_as_planned_at_the_start(seed):
    assert impossible_at_start(random_shift(seed)) == {}


@pytest.mark.parametrize("seed", range(30))
def test_random_shift_survives_its_surprises_without_violations(seed):
    scenario = random_shift(seed)
    kinds = {e.type for e in scenario.demo_events}
    assert scenario.auto_events and "change_priority" in kinds and all(e.source == "surprise" for e in scenario.demo_events)
    run = run_to_end(start(scenario, "coordinator"))
    assert not run.pending_events and metrics(run)["invariant_violations"] == 0
    assert all(t.status != TractorStatus.BROKEN for t in run.world.tractors.values()) is ("breakdown" not in kinds)


def test_make_feasible_moves_an_impossible_deadline_and_says_so(scenario):
    tight = scenario.model_copy(update={"jobs": [j.model_copy(update={"deadline": 0.5}) if j.id == "J05" else j for j in scenario.jobs]})
    assert "J05" in impossible_at_start(tight)
    fixed, changes = make_feasible(tight)
    assert impossible_at_start(fixed) == {}
    assert any(c.startswith("J05: deadline moved from 06:30") for c in changes)


def test_make_feasible_removes_a_job_no_tractor_can_do(scenario):
    sprayers_only = scenario.model_copy(update={"tractors": [t for t in scenario.tractors if t.implement.value == "sprayer"]})
    fixed, changes = make_feasible(sprayers_only)
    assert all(j.type == "spray" for j in fixed.jobs)
    assert any("removed: no tractor has a mower" in c for c in changes)


def test_priority_change_on_finished_work_is_ignored(scenario):
    run = run_to_end(start(scenario, "coordinator", with_demo_events=False))
    done = next(j.id for j in run.world.jobs.values() if j.status == JobStatus.DONE)
    assert apply_event(run, EventIn(at=run.world.time, type="change_priority", job_id=done, priority=1)) is run


# --- deadline risk -----------------------------------------------------------


def test_outlook_covers_every_planned_job_and_none_is_late(world):
    planned = replan(world).world
    ahead = outlook(planned, build_network(planned))
    queued = {jid for t in planned.tractors.values() for jid in t.queue}
    assert set(ahead) == queued and all(o.slack >= -1e-6 for o in ahead.values())


def test_job_with_little_spare_time_is_flagged_and_announced(world):
    network = build_network(world)
    planned = replan(world, network, Recorder)
    ahead = outlook(planned.world, network)
    job_id, tight = next(iter(ahead.items()))
    squeezed = replace(world, jobs={**world.jobs, job_id: replace(world.jobs[job_id], deadline=tight.finish + 0.2)})
    result = replan(squeezed, network, Recorder)
    risky = [o.job_id for o in at_risk(result.world, network)]
    messages = transcript(squeezed, network, {"type": "initial_plan"}, {}, result)
    assert risky and {m.topic for m in messages if m.kind == "risk"} == set(risky)
