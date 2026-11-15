# Run the Fleet: Fleet Coordinator

A coordinator that assigns jobs to a small fleet of simulated autonomous tractors and **re-plans the moment one breaks down, without losing or duplicating work**. Built for the American Tractor Company "Run the Fleet" track.

- **Algorithm first, LLM second.** Hard constraints (implement, fuel, deadline) are enforced in code. Claude only explains plan changes, answers "why?", and turns operator text into typed events that the coordinator validates before anything runs.
- **Our own lightweight simulation** (not AgOpenWeb): a 10×10 grid, roads between fields, travel time = distance / speed.
- **One re-plan function for every event**: breakdown, blocked road and changed priority all call `replan(world)`.
- **Provable safety**: invariants are checked after every re-plan. If a check fails, the new plan is thrown away and the last valid one is kept.

## Run it

```bash
# backend (Python 3.11+)
cd backend
python3 -m venv .venv && .venv/bin/pip install fastapi 'uvicorn[standard]' pydantic anthropic python-dotenv pytest pytest-cov httpx
cp .env.example .env            # optional: add ANTHROPIC_API_KEY for Claude explanations
.venv/bin/uvicorn api.main:app --port 8000

# frontend
cd frontend && npm install && npm run dev   # http://localhost:5173
```

Without an API key everything still works: explanations come from templates, and the copilot uses a small offline parser.

```bash
cd backend
.venv/bin/pytest --cov=fleet --cov=api --cov=llm   # 38 tests
.venv/bin/python -m scripts.benchmark --n 50       # coordinator vs baseline table
.venv/bin/python -m scripts.export_demo            # writes results/
```

## Results

Coordinator vs first-come-first-served baseline over 50 random scenarios, with the same breakdowns for both (`results/comparison.md`):

| metric (mean) | coordinator | baseline |
|---|---|---|
| jobs completed on time | **6.32** | 4.84 |
| priority-1 jobs completed | **2.6** | 1.72 |
| travel hours | **6.59** | 7.19 |
| idle hours | **3.26** | 3.52 |
| constraint violations | **0** | 0 |

The coordinator wins 42 scenarios, ties 8 and loses 0.

## Deliverables

| Item | Where |
|---|---|
| Scenario (tractors, fields, jobs) | `backend/scenario.json` |
| Event log of the demo run | `results/demo_event_log.json` (also via the "Event log" button) |
| Baseline comparison | `results/comparison.md`, `results/benchmark.json` |

## How the coordinator works (`backend/fleet/`)

1. **Filter** (`feasibility.py`): a tractor's whole queue is simulated in order. Each job needs the right implement, enough fuel for travel plus work, and must finish before its deadline. Inserting a job early can break a later one, so the whole queue is checked every time.
2. **Score and assign** (`coordinator.py`): jobs are sorted by priority, then deadline. Each one goes into the cheapest feasible slot across all queues. The objective is lexicographic: priority-weighted completed work first, then travel, then completion time.
3. **Improve**: deterministic local search (relocate, swap, insert-unassigned, eject-and-insert) with a fixed iteration cap, so the same input always gives the same plan.
4. **Re-plan on an event** (`replan.py`): completed work is frozen, jobs currently in progress on healthy tractors stay pinned, the finished share of an interrupted job is kept, and everything else is planned again.
5. **Verify** (`invariants.py`): each job has at most one tractor; completed work is never reassigned; every queue satisfies implement, fuel and deadline; every unfinished job is either planned or marked unassignable with a reason.

**Baseline rule** (`baseline.py`): whenever a tractor is free, it takes the first pending job in submission order that it can feasibly do right now. No lookahead, no priorities. Work released by a breakdown goes back to the pool with its progress kept.

**Metric definitions**: *completed* means done before the deadline. *Idle* is time a healthy tractor sits without work while unfinished, assignable work still exists. Fuel cannot be refilled during a shift.

## LLM (`backend/llm/claude.py`)

`claude-opus-5-5` at low effort with structured outputs, plus server-side refusal fallbacks. The model only ever sees structured facts: the plan diff, the score breakdown, or a summary of the state. Copilot proposals are shown as an "Understood as … Apply / Cancel" card, and the coordinator validates every event before executing it.
