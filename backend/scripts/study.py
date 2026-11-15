"""Large comparison: the coordinator against FCFS and EDF over many generated shifts.

Writes results/study.md (tables with explanations) and results/study.json (the numbers).
Run from backend/:  .venv/bin/python -m scripts.study --n 300
"""

from __future__ import annotations

import argparse
import json
from multiprocessing import Pool
from pathlib import Path

from fleet.engine import metrics, run_to_end, start
from fleet.generate import random_shift
from fleet.scenario import ScenarioIn, random_scenario

RESULTS = Path(__file__).resolve().parents[2] / "results"
STRATEGIES = ("coordinator", "baseline", "edf")
NAMES = {"coordinator": "Coordinator", "baseline": "FCFS", "edf": "EDF"}
FAMILIES = {
    "benchmark": "Benchmark: 10 jobs, 3 tractors, one breakdown, deadlines not adjusted",
    "none": "Calm: random shift, nothing goes wrong",
    "low": "Some trouble: random shift, one or two events",
    "high": "Rough day: random shift, breakdown, closed roads, priority change, weather",
}
SUMMED = ("jobs_completed", "priority1_completed", "priority_score", "travel_hours", "idle_hours", "makespan_hours", "unassignable", "invariant_violations")
HIGHER_IS_BETTER = ("jobs_completed", "priority1_completed", "priority_score")
TIE_KEYS = ("priority_score", "travel_hours", "idle_hours")
EPS = 1e-9

ROWS = (
    ("jobs_completed", "Jobs done on time", 2),
    ("share_done", "Share of all jobs done on time", 3),
    ("priority1_completed", "Urgent (P1) jobs done on time", 2),
    ("priority_score", "Priority-weighted output", 1),
    ("travel_hours", "Driving, hours", 2),
    ("travel_per_job", "Driving per job done, hours", 2),
    ("idle_hours", "Idle, hours", 2),
    ("unassignable", "Jobs not done", 2),
    ("makespan_hours", "Length of the shift, hours", 2),
)

EXPLANATIONS = """## What each number means

- **Jobs done on time**: a job counts only if it is finished before its own deadline. Mean per shift.
- **Share of all jobs done on time**: the same thing as a fraction of every job in the shift.
- **Urgent (P1) jobs done on time**: the same count, for the highest priority only.
- **Priority-weighted output**: 4 points for an urgent job, 2 for a normal one, 1 for a low one. It shows whether the extra jobs are the important ones.
- **Driving, hours**: total time all tractors spent on the road between fields and the depot.
- **Driving per job done**: driving divided by jobs done on time. A dispatcher that finishes more jobs also drives to more fields, so this is the fair way to compare driving.
- **Idle, hours**: time a healthy tractor stands with nothing to do while unfinished work for its implement is still waiting. A tractor held at a field by the weather is not counted as idle.
- **Jobs not done**: jobs that could not be finished in time (deadline missed, or no working tractor with the right implement).
- **Length of the shift**: when the last piece of work ended. A dispatcher that gives up on jobs early finishes sooner.
- **Constraint violations**: plans that broke a rule (two tractors on one job, wrong implement, not enough fuel, missed deadline, a job lost track of). Counted by the Safety Agent on every re-plan.

The two dispatchers we compare with never plan ahead. **FCFS** (first come, first served) is the starter rule from the brief: a free tractor takes the first job in the list it can do. **EDF** (earliest deadline first) is a stronger rule we added: a free tractor takes the job whose deadline is nearest.
"""

CAVEATS = """## Read this before quoting the numbers

- **Three of the four families lean our way by construction.** The Calm, Some trouble and Rough day shifts are adjusted so that the coordinator's own opening plan can finish every job. The Benchmark family is not adjusted, so it is the fairest comparison, and it says the same thing.
- **Total driving is about level with FCFS.** We finish more jobs, so we visit more fields. The gain is in driving per job, not in total hours.
- **Our shift is longer.** We keep working on jobs that FCFS has already given up on.
- **We do lose some shifts.** A breakdown or another event can hit a plan that was the best one before it happened.
- The weather and the events are scripted by the simulator; none of this is field data.
"""


def _scenario(family: str, seed: int) -> ScenarioIn:
    return random_scenario(seed) if family == "benchmark" else random_shift(seed, trouble=family)  # type: ignore[arg-type]


def _one(task: tuple[str, int]) -> dict:
    family, seed = task
    scenario = _scenario(family, seed)
    finished = {s: run_to_end(start(scenario, s)) for s in STRATEGIES}
    recoveries = [
        e.data["trace"]["recovery"]["event_to_plan_ms"]
        for e in finished["coordinator"].log
        if e.kind == "replan" and e.data["trace"]["recovery"]["event_to_plan_ms"] is not None
    ]
    return {
        "family": family,
        "jobs": len(scenario.jobs),
        "runs": {s: {k: metrics(run)[k] for k in SUMMED} for s, run in finished.items()},
        "recoveries_ms": recoveries,
    }


def _better(key: str, ours: float, theirs: float) -> int:
    """+1 when we are better on this metric, -1 when worse, 0 when level."""
    gap = ours - theirs if key in HIGHER_IS_BETTER else theirs - ours
    return (gap > EPS) - (gap < -EPS)


def summarise(rows: list[dict]) -> dict:
    n = len(rows)
    means: dict[str, dict[str, float]] = {}
    for s in STRATEGIES:
        total = {k: sum(r["runs"][s][k] for r in rows) for k in SUMMED}
        done = total["jobs_completed"]
        means[s] = {
            **{k: total[k] / n for k in SUMMED},
            "share_done": done / sum(r["jobs"] for r in rows),
            "travel_per_job": total["travel_hours"] / done if done else 0.0,
            "violations_total": total["invariant_violations"],
        }
    out: dict = {"shifts": n, "jobs_per_shift": sum(r["jobs"] for r in rows) / n, "mean": means}
    times = sorted(ms for r in rows for ms in r["recoveries_ms"])
    if times:
        out["recovery_ms"] = {
            "events": len(times),
            "median": times[len(times) // 2],
            "p95": times[min(len(times) - 1, int(len(times) * 0.95))],
            "max": times[-1],
        }
    for other in ("baseline", "edf"):
        ours, theirs = means["coordinator"], means[other]
        out[f"percent_vs_{other}"] = {k: (ours[k] - theirs[k]) / theirs[k] * 100 if theirs[k] else None for k, _, _ in ROWS}
        verdicts = [_better("jobs_completed", r["runs"]["coordinator"]["jobs_completed"], r["runs"][other]["jobs_completed"]) for r in rows]
        ties = [r for r, v in zip(rows, verdicts) if v == 0]
        out[f"jobs_vs_{other}"] = {"wins": verdicts.count(1), "ties": len(ties), "losses": verdicts.count(-1)}
        per_key = {}
        for key in TIE_KEYS:
            marks = [_better(key, r["runs"]["coordinator"][key], r["runs"][other][key]) for r in ties]
            per_key[key] = {"better": marks.count(1), "same": marks.count(0), "worse": marks.count(-1)}
        ahead_somewhere = sum(any(_better(k, r["runs"]["coordinator"][k], r["runs"][other][k]) > 0 for k in TIE_KEYS) for r in ties)
        out[f"ties_vs_{other}"] = {**per_key, "better_on_at_least_one": ahead_somewhere}
    return out


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.1f}%"


def _table(summary: dict) -> list[str]:
    lines = ["| Metric | Coordinator | FCFS | EDF | vs FCFS | vs EDF |", "|---|---|---|---|---|---|"]
    for key, label, digits in ROWS:
        values = " | ".join(f"{summary['mean'][s][key]:.{digits}f}" for s in STRATEGIES)
        lines.append(f"| {label} | {values} | {_pct(summary['percent_vs_baseline'][key])} | {_pct(summary['percent_vs_edf'][key])} |")
    return lines


def _share(part: int, whole: int) -> str:
    return f"{part} ({part / whole:.0%})" if whole else "0"


def render(report: dict, n: int) -> str:
    whole = report["all"]
    shifts = whole["shifts"]
    lines = [
        "# Coordinator against two simple dispatchers",
        "",
        f"{shifts} generated shifts ({n} in each of four families), every shift run under all three strategies: {shifts * len(STRATEGIES)} simulated shifts in total. "
        f"On average a shift has {whole['jobs_per_shift']:.1f} jobs. Reproduce with `python -m scripts.study --n {n}` from `backend/`.",
        "",
        "## Headline",
        "",
        f"- **{_pct(whole['percent_vs_baseline']['jobs_completed'])} jobs done on time against FCFS**, and {_pct(whole['percent_vs_edf']['jobs_completed'])} against EDF.",
        f"- **{_pct(whole['percent_vs_baseline']['priority1_completed'])} urgent jobs** against FCFS.",
        f"- **{_pct(whole['percent_vs_baseline']['idle_hours'])} idle time** and **{_pct(whole['percent_vs_baseline']['travel_per_job'])} driving per job** against FCFS; total driving is {_pct(whole['percent_vs_baseline']['travel_hours'])}.",
        f"- **{int(whole['mean']['coordinator']['violations_total'])} constraint violations** in {shifts} shifts.",
        "",
        "## All shifts together",
        "",
        "Means per shift. The last two columns are the coordinator's difference from each dispatcher; for driving, idle time and jobs not done, a negative number is good.",
        "",
        *_table(whole),
        "",
        "### Who finishes more jobs, shift by shift",
        "",
        "| Against | Coordinator ahead | Level | Coordinator behind |",
        "|---|---|---|---|",
    ]
    for other in ("baseline", "edf"):
        w = whole[f"jobs_vs_{other}"]
        lines.append(f"| {NAMES[other]} | {_share(w['wins'], shifts)} | {_share(w['ties'], shifts)} | {_share(w['losses'], shifts)} |")
    lines += ["", "### When the job count is level", "", "The same number of jobs does not mean the same shift. On the shifts where both finished equally many jobs:", ""]
    for other in ("baseline", "edf"):
        t, ties = whole[f"ties_vs_{other}"], whole[f"jobs_vs_{other}"]["ties"]
        lines += [
            f"**Against {NAMES[other]}** ({ties} level shifts): the coordinator is ahead on at least one of priority-weighted output, driving or idle time in {_share(t['better_on_at_least_one'], ties)} of them.",
            "",
            "| Metric | Coordinator better | Same | Coordinator worse |",
            "|---|---|---|---|",
            f"| Priority-weighted output | {t['priority_score']['better']} | {t['priority_score']['same']} | {t['priority_score']['worse']} |",
            f"| Driving | {t['travel_hours']['better']} | {t['travel_hours']['same']} | {t['travel_hours']['worse']} |",
            f"| Idle time | {t['idle_hours']['better']} | {t['idle_hours']['same']} | {t['idle_hours']['worse']} |",
            "",
        ]
    rec = whole.get("recovery_ms")
    if rec:
        lines += [
            "## How fast the fleet recovers",
            "",
            f"Wall-clock time from an event reaching the coordinator to a new plan that has passed the safety checks, over {rec['events']} events "
            f"(breakdowns, closed roads, priority changes, weather): **median {rec['median']:.1f} ms, 95th percentile {rec['p95']:.1f} ms, slowest {rec['max']:.1f} ms**.",
            "",
            "This is the planner and the safety checks only, measured on one laptop core per shift with eight shifts running at once. It does not include the network, "
            "the browser, or the LLM explanation, which is written afterwards and never holds the plan up. The slowed-down conversation in the Radio tab is a replay for the reader, not this time.",
            "",
        ]
    lines += ["## By kind of shift", ""]
    for family, title in FAMILIES.items():
        s = report[family]
        f, e = s["jobs_vs_baseline"], s["jobs_vs_edf"]
        lines += [
            f"### {title}",
            "",
            f"{s['shifts']} shifts, {s['jobs_per_shift']:.1f} jobs each. By jobs done on time: against FCFS {f['wins']} ahead, {f['ties']} level, {f['losses']} behind; "
            f"against EDF {e['wins']} ahead, {e['ties']} level, {e['losses']} behind.",
            "",
            *_table(s),
            "",
        ]
    return "\n".join([*lines, EXPLANATIONS, CAVEATS])


def run_study(n: int, workers: int) -> dict:
    tasks = [(family, seed) for family in FAMILIES for seed in range(n)]
    with Pool(workers) as pool:
        rows = pool.map(_one, tasks, chunksize=8)
    report = {family: summarise([r for r in rows if r["family"] == family]) for family in FAMILIES}
    return {**report, "all": summarise(rows)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=300, help="shifts per family")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    report = run_study(args.n, args.workers)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "study.json").write_text(json.dumps(report, indent=2))
    (RESULTS / "study.md").write_text(render(report, args.n))


if __name__ == "__main__":
    main()
