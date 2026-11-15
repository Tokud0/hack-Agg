# Run the Fleet: Fleet Coordinator

A coordinator that assigns jobs to a small fleet of simulated autonomous tractors and **re-plans the moment one breaks down, without losing or duplicating work**. Built for the American Tractor Company "Run the Fleet" track.

- **Algorithm first, LLM second.** Hard constraints (implement, fuel, deadline) are enforced in code. The LLM (Groq `openai/gpt-oss-120b`, with Claude as an alternative) only explains plan changes, answers "why?" and chat questions, narrates what-if forecasts, and turns operator text into typed events or job drafts that the coordinator validates before anything runs.
- **Our own lightweight simulation** (not AgOpenWeb): a 10×10 grid, roads between fields, travel time = distance / speed.
- **One re-plan function for every event**: breakdown, blocked road and changed priority all call `replan(world)`.
- **Provable safety**: invariants are checked after every re-plan. If a check fails, the new plan is thrown away and the last valid one is kept.

## Run it

```bash
# backend (Python 3.11+)
cd backend
python3 -m venv .venv && .venv/bin/pip install fastapi 'uvicorn[standard]' pydantic anthropic python-dotenv pytest pytest-cov httpx
cp .env.example .env            # optional: GROQ_API_KEY (or ANTHROPIC_API_KEY) for AI text
.venv/bin/uvicorn api.main:app --port 8000

# frontend
cd frontend && npm install && npm run dev   # http://localhost:5173
```

Without an API key everything still works: explanations come from templates, and the copilot and job intake use small offline parsers.

## Dashboard

- **Baseline vs coordinator** shown side by side on the same scenario, with live counters and the coordinator's lead over the baseline.
- **Map**: fields fill in as they are worked, each tractor has a fuel ring and a planned route, hovering a tractor shows its status, and arrows show work handed over after a breakdown.
- **Fleet status cards** for every tractor, each with a *Simulate breakdown* button.
- **Schedule (Gantt)**: blocks slide between tractors on a re-plan; deadlines and events are marked.
- **Safety checks**: the 4 invariants and how long the re-plan took, updated after every re-plan.
- **What changed & why**: an AI explanation of every re-plan.
- **Tools**:
  - *Copilot chat*: ask questions or report events, then confirm them.
  - *Add jobs*: free text turned into editable drafts, a manual form, or a scenario JSON upload.
  - *Events & what-if*: forecast a disruption without touching the live plan, or apply it now.
- Click any job for **"why?"**: the score breakdown and every rejected alternative.

```bash
cd backend
.venv/bin/pytest --cov=fleet --cov=api --cov=llm   # 44 tests
.venv/bin/python -m scripts.benchmark --n 50       # coordinator vs baseline table
.venv/bin/python -m scripts.export_demo            # writes results/
```

## Results

Our coordinator against two greedy dispatchers that never plan ahead: **FCFS** (first come, first served) and **EDF** (earliest deadline first). All three run the same 50 random scenarios with the same breakdowns (`results/comparison.md`):

| metric (mean of 50) | coordinator | EDF | FCFS |
|---|---|---|---|
| jobs completed on time | **6.36** | 5.88 | 4.80 |
| urgent (P1) jobs completed | **2.54** | 1.96 | 1.70 |
| priority-weighted output | **16.1** | 13.7 | 11.3 |
| driving hours | **6.49** | 7.41 | 7.13 |
| idle hours | **0.10** | 0.37 | 0.40 |
| constraint violations | **0** | 0 | 0 |

By jobs completed, the coordinator wins 44, ties 5 and loses 1 against FCFS; against EDF it wins 26, ties 17 and loses 7. On priority-weighted output it wins 40, ties 4 and loses 6 against EDF. Without breakdowns it never loses to EDF on priority-weighted output. The remaining losses happen when a breakdown hits a plan that was optimal before the breakdown.

Demo scenario, with T1 breaking down at 08:00: the coordinator completes 8 jobs, 3 of them urgent, with one refuel stop. EDF completes 7 (2 urgent) and FCFS 7 (1 urgent).

## Deliverables

| Item | Where |
|---|---|
| Scenario (tractors, fields, jobs) | `backend/scenario.json` |
| Event log of the demo run | `results/demo_event_log.json` (also via the "Event log" button) |
| Baseline comparison | `results/comparison.md`, `results/benchmark.json` |

## How the coordinator works (`backend/fleet/`)

1. **Filter** (`feasibility.py`): a tractor's whole queue is simulated in order. Each job needs the right implement, enough fuel for travel plus work, and must finish before its deadline. Inserting a job early can break a later one, so the whole queue is checked every time.
2. **Score and assign** (`coordinator.py`): jobs are sorted by priority, then deadline. Each one goes into the cheapest feasible slot across all queues. The objective is lexicographic: priority-weighted completed work first, then travel, then completion time.
3. **Improve**: multi-start. Several starting plans (by priority, by deadline, by slack, an EDF schedule, and fixed-seed shuffles) are each improved by local search (relocate, swap, insert-unassigned, eject-and-insert) with a fixed iteration cap, and the best one wins. The search is deterministic.
4. **Re-plan on an event** (`replan.py`): completed work is frozen, jobs currently in progress on healthy tractors stay pinned, the finished share of an interrupted job is kept, and everything else is planned again.
5. **Verify** (`invariants.py`): each job has at most one tractor; completed work is never reassigned; every queue satisfies implement, fuel and deadline; every unfinished job is either planned or marked unassignable with a reason.

**Baseline rules** (`baseline.py`): whenever a tractor is free, it takes the first pending job it can feasibly do right now, either in submission order (FCFS) or by earliest deadline (EDF). There is no lookahead. Work released by a breakdown goes back to the pool with its progress kept.

**Metric definitions**: *completed* means done before the deadline. *Idle* is time a healthy tractor sits without work while unfinished, assignable work for its implement is still waiting.

**Fuel and refuelling** (`feasibility.plan_leg`, shared by the planner and the simulator): a tractor always keeps enough fuel to drive back to the depot. That reserve is what lets it take over work after a breakdown. When a job plus the way home does not fit in the tank, the tractor first refuels at the depot (`refuel_hours`, 15 min in the demo). Refuel stops count against deadlines.

## LLM (`backend/llm/`)

`provider.py` uses Groq (`GROQ_MODEL`, default `openai/gpt-oss-120b`, strict JSON-schema output) when `GROQ_API_KEY` is set, otherwise Claude (`claude-opus-5-5`) when `ANTHROPIC_API_KEY` is set, otherwise templates. `assistant.py` holds the features. The model only ever sees structured facts: the plan diff, the score breakdown, the forecast numbers, or a summary of the state. Copilot proposals appear as an "Understood as … Apply / Cancel" card, and every event and job is validated by the coordinator before it runs.
