| metric (mean of 50) | coordinator | EDF | FCFS |
|---|---|---|---|
| jobs_completed | 6.3 | 5.88 | 4.8 |
| priority1_completed | 2.52 | 1.96 | 1.7 |
| priority_score | 15.92 | 13.68 | 11.34 |
| travel_hours | 6.57 | 7.41 | 7.13 |
| travel_per_job | 1.04 | 1.26 | 1.48 |
| idle_hours | 0.05 | 0.37 | 0.4 |
| refuel_stops | 0 | 0 | 0 |
| invariant_violations | 0 | 0 | 0 |

vs FCFS: wins 43 · ties 5 · losses 2

vs EDF: wins 25 · ties 19 · losses 6

vs EDF, priority-weighted: wins 39 · ties 5 · losses 6

Demo scenario (T1 breaks down at 08:00):

| metric | coordinator | EDF | FCFS |
|---|---|---|---|
| jobs_completed | 8 | 7 | 7 |
| priority1_completed | 3 | 2 | 1 |
| priority_score | 20.0 | 16.0 | 14.0 |
| travel_hours | 11.96 | 9.0 | 10.66 |
| travel_per_job | 1.49 | 1.29 | 1.52 |
| idle_hours | 0.04 | 1.5 | 0.29 |
| refuel_stops | 1 | 0 | 1 |
| invariant_violations | 0 | 0 | 0 |
