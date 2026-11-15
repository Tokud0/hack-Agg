"""Agent conversation: the plan search, told as messages between tractor agents.

Each tractor agent answers only for itself. The coordinator announces a job, every tractor replies
with a bid or the reason it cannot take it, the best bid wins and the winner claims the job so no
one else plans for it. Tractors then trade jobs whenever that improves the plan, and the safety
gate approves or vetoes the result.

Nothing here decides anything: the messages are recorded by observing the planner
(`coordinator.replay_winner`), and every number in a bid comes from the same feasibility code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .coordinator import (
    AwardRule,
    Candidate,
    PlanningInput,
    Queues,
    _eval,
    _queue_cost,
    build_input,
    replay_winner,
)
from .models import TractorStatus, World
from .replan import ReplanResult
from .routing import RoadNetwork

COORDINATOR = "coordinator"
SAFETY_GATE = "safety_gate"
EVERYONE = "all"
SHIFT_START_HOUR = 6.0
AWARD_REASON: dict[str, str] = {"cheapest": "lowest added cost", "soonest": "soonest finish"}


@dataclass(frozen=True)
class Message:
    sender: str
    to: str
    kind: str  # note | alert | status | announce | bid | decline | award | claim | no_taker | trade | agree | flag | verdict | ack
    phase: str  # situation | auction | negotiation | approval
    text: str
    topic: str = ""  # the job (or jobs) the message is about
    data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Bid:
    """One tractor's answer to an announced job."""

    tractor_id: str
    ok: bool
    reason: str = ""
    value: float = 0.0  # what the award compares; lower wins
    finish: float = 0.0
    extra_travel: float = 0.0
    queue: tuple[str, ...] = ()


def clock(hours: float) -> str:
    total = max(0, round((SHIFT_START_HOUR + hours) * 60))
    return f"{total // 60 % 24:02d}:{total % 60:02d}"


def _jobs(ids) -> str:
    return ", ".join(ids)


# --- situation: who is where, what just happened -----------------------------


def _trigger_messages(world: World, trigger: dict, released: dict[str, str]) -> list[Message]:
    kind = trigger.get("type")
    if kind == "initial_plan":
        open_jobs = sum(1 for j in world.jobs.values() if j.status.value != "done")
        return [Message(COORDINATOR, EVERYONE, "note", "situation", f"Shift start: {open_jobs} jobs to hand out. Report your status.")]
    if kind == "breakdown":
        tid = str(trigger["tractor_id"])
        gave_up = f"I release {_jobs(sorted(released))}." if released else "I had no work queued."
        return [
            Message(tid, EVERYONE, "alert", "situation", f"I have broken down near {world.tractors[tid].node}. {gave_up}",
                    data={"released": sorted(released)}),
            Message(COORDINATOR, EVERYONE, "note", "situation", f"{tid} is out. Re-opening the auction for all open work. Report your status."),
        ]
    if kind == "block_road":
        text = f"Road {trigger['a']}–{trigger['b']} is closed, routes have changed."
    elif kind == "change_priority":
        text = f"{trigger['job_id']} is now priority P{trigger['priority']}."
    elif kind == "add_job":
        text = f"New job {trigger['job_id']} on {trigger['field_id']} (P{trigger['priority']})."
    else:
        text = f"Event: {kind}."
    return [Message(COORDINATOR, EVERYONE, "alert", "situation", f"{text} Re-opening the auction for all open work. Report your status.")]


def _status_message(world: World, tractor_id: str) -> Message:
    t = world.tractors[tractor_id]
    base = f"{t.implement.value.capitalize()}, at {t.node}, fuel {t.fuel:.0f}/{t.fuel_capacity:.0f}."
    job = world.jobs.get(t.current_job) if t.current_job else None
    if job is None:
        doing = "Free now."
    elif t.status == TractorStatus.WORKING:
        doing = f"Working on {job.id} ({job.progress:.0%} done). I keep it."
    else:
        doing = f"On my way to {job.field_id} for {job.id}. I keep it."
    return Message(tractor_id, EVERYONE, "status", "situation", f"{base} {doing}",
                   data={"node": t.node, "fuel": round(t.fuel), "current_job": t.current_job})


def situation(world: World, trigger: dict, released: dict[str, str]) -> list[Message]:
    working = [tid for tid in sorted(world.tractors) if world.tractors[tid].status != TractorStatus.BROKEN]
    return [*_trigger_messages(world, trigger, released), *(_status_message(world, tid) for tid in working)]


# --- auction and negotiation: recorded from the planner ----------------------


def make_bid(inp: PlanningInput, queues: Queues, tractor_id: str, job_id: str, rule: AwardRule) -> Bid:
    """What this tractor would answer, computed exactly as the planner computes it."""
    tractor = next(t for t in inp.tractors if t.id == tractor_id)
    job = inp.world.jobs[job_id]
    if tractor.implement != job.implement:
        return Bid(tractor_id, False, f"I carry a {tractor.implement.value}, this needs a {job.implement.value}")
    queue = queues[tractor_id]
    base = _eval(inp, tractor, queue)
    base_cost = _queue_cost(inp, base) if base.ok else 0.0
    positions = [len(queue)] if rule == "soonest" else range(len(queue) + 1)
    best: Bid | None = None
    for pos in positions:
        candidate = queue[:pos] + (job_id,) + queue[pos:]
        ev = _eval(inp, tractor, candidate)
        if not ev.ok:
            continue
        finish = ev.finish_times[job_id]
        value = finish if rule == "soonest" else _queue_cost(inp, ev) - base_cost
        if best is None or value < best.value - 1e-9:
            best = Bid(tractor_id, True, "", value, finish, ev.travel_hours - (base.travel_hours if base.ok else 0.0), candidate)
    if best is not None:
        return best
    return Bid(tractor_id, False, _eval(inp, tractor, queue + (job_id,)).reason or "no feasible slot in my queue")


def _owners(queues: Queues) -> dict[str, str]:
    return {jid: tid for tid, q in queues.items() for jid in q}


class _Recorder:
    """Collects messages while the planner replays its winning round."""

    def __init__(self, inp: PlanningInput) -> None:
        self.inp = inp
        self.auction: list[Message] = []
        self.trades: list[Message] = []

    def on_award(self, job_id: str, queues: Queues, winner: str | None, rule: AwardRule) -> None:
        job = self.inp.world.jobs[job_id]
        say = self.auction.append
        say(Message(COORDINATOR, EVERYONE, "announce", "auction", topic=job_id,
                    text=f"Who takes {job_id}? {job.type.capitalize()} on {job.field_id}, P{job.priority}, "
                         f"{job.remaining_hours:.1f} h of work, due {clock(job.deadline)}.",
                    data={"field_id": job.field_id, "priority": job.priority, "deadline": job.deadline}))
        winning_queue: tuple[str, ...] = ()
        for tractor in self.inp.tractors:
            bid = make_bid(self.inp, queues, tractor.id, job_id, rule)
            if not bid.ok:
                say(Message(tractor.id, COORDINATOR, "decline", "auction", f"I pass: {bid.reason}.", job_id))
                continue
            is_winner = tractor.id == winner
            winning_queue = bid.queue if is_winner else winning_queue
            say(Message(tractor.id, COORDINATOR, "bid", "auction", topic=job_id,
                        text=f"I can finish it by {clock(bid.finish)}, with {bid.extra_travel:.1f} h more driving.",
                        data={"value": round(bid.value, 2), "finish": round(bid.finish, 2),
                              "extra_travel": round(bid.extra_travel, 2), "is_winner": is_winner}))
        if winner is None:
            say(Message(COORDINATOR, EVERYONE, "no_taker", "auction", f"No one can take {job_id} right now. It stays in the pool.", job_id))
            return
        say(Message(COORDINATOR, winner, "award", "auction", f"{job_id} goes to {winner}: {AWARD_REASON[rule]}.", job_id))
        say(Message(winner, EVERYONE, "claim", "auction", f"{job_id} is mine. Nobody else needs to plan for it.", job_id,
                    data={"queue": list(winning_queue)}))

    def on_trade(self, before: Queues, after: Queues, gain: float) -> None:
        old, new = _owners(before), _owners(after)
        moved = [(jid, old.get(jid), new.get(jid)) for jid in sorted(set(old) | set(new)) if old.get(jid) != new.get(jid)]
        data = {"queues": {tid: list(q) for tid, q in after.items()}, "gain": round(gain, 1)}
        topic = _jobs(jid for jid, _, _ in moved)
        better = f"The plan gets better by {gain:.0f} points."

        def say(sender: str, to: str, kind: str, text: str, payload: dict | None = None) -> None:
            self.trades.append(Message(sender, to, kind, "negotiation", text, topic, payload or {}))

        if not moved:
            tid = next(t for t in after if after[t] != before.get(t))
            say(tid, EVERYONE, "trade", f"I am reordering my own queue to {' → '.join(after[tid])}. {better}", data)
        elif len(moved) == 1 and moved[0][1] is None:
            jid, _, taker = moved[0]
            say(taker, COORDINATOR, "trade", f"I found room for {jid} after all. {better}", data)
        elif len(moved) == 1:
            jid, giver, taker = moved[0]
            say(taker, giver, "trade", f"Hand me {jid}, it fits my route better. {better}")
            say(giver, taker, "agree", f"Agreed, {jid} is yours.", data)
        elif len(moved) == 2 and all(a and b for _, a, b in moved):
            (job_a, first, second), (job_b, _, _) = moved
            say(first, second, "trade", f"Swap? You take {job_a}, I take {job_b}. {better}")
            say(second, first, "agree", f"Agreed: {job_a} is mine, {job_b} is yours.", data)
        else:
            taken = [jid for jid, _, b in moved if b]
            dropped = [jid for jid, _, b in moved if b is None]
            tid = next(b for _, _, b in moved if b)
            say(tid, COORDINATOR, "trade", f"I give {_jobs(dropped)} back to the pool and take {_jobs(taken)} instead: worth more. {better}", data)


def negotiation(inp: PlanningInput, candidates: tuple[Candidate, ...]) -> list[Message]:
    winner = next((c for c in candidates if c.is_winner), None)
    if winner is None:
        return [Message(COORDINATOR, EVERYONE, "note", "auction", "No open job can be handed out right now.")]
    recorder = _Recorder(inp)
    replay_winner(inp, candidates, recorder.on_award, recorder.on_trade)
    intro = Message(COORDINATOR, EVERYONE, "note", "auction",
                    f"I ran this auction {len(candidates)} times, announcing the jobs in a different order each time. "
                    f"Best outcome: \"{winner.name}\". This is that round.")
    return [intro, *recorder.auction, *recorder.trades]


# --- approval: the safety gate and the tractors' confirmations ---------------


def approval(result: ReplanResult) -> list[Message]:
    report = result.report
    if not result.accepted:
        return [Message(SAFETY_GATE, COORDINATOR, "verdict", "approval",
                        f"VETO. {'; '.join(report.violations)}. Keep the last valid plan.", data={"accepted": False})]
    flags = [
        Message(COORDINATOR, EVERYONE, "flag", "approval", f"{jid} cannot be done this shift: {reason}. Flagged for the operator.", jid)
        for jid, reason in sorted(result.plan.unassignable.items())
    ]
    verdict = Message(SAFETY_GATE, COORDINATOR, "verdict", "approval",
                      f"Checked the final plan against {len(report.checked)} safety rules: one tractor per job, finished work untouched, "
                      "implement / fuel / deadline, no job lost. All pass. Approved.", data={"accepted": True})
    acks = []
    for tid in sorted(result.world.tractors):
        tractor = result.world.tractors[tid]
        if tractor.status == TractorStatus.BROKEN:
            continue
        first = f"Finishing {tractor.current_job}, then " if tractor.current_job else ""
        queue = " → ".join(tractor.queue) or "nothing queued"
        acks.append(Message(tid, COORDINATOR, "ack", "approval", f"Confirmed. {first}{queue}.", data={"queue": list(tractor.queue)}))
    return [*flags, verdict, *acks]


def transcript(
    world: World, network: RoadNetwork, trigger: dict, released: dict[str, str], result: ReplanResult
) -> tuple[Message, ...]:
    """The whole conversation of one re-plan. `world` is the state the planner saw (after the event)."""
    inp = build_input(world, network)
    return (*situation(world, trigger, released), *negotiation(inp, result.candidates), *approval(result))
