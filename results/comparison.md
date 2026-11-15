| metric (mean of 50) | coordinator | EDF | FCFS |
|---|---|---|---|
| jobs_completed | 6.36 | 5.88 | 4.8 |
| priority1_completed | 2.54 | 1.96 | 1.7 |
| priority_score | 16.1 | 13.68 | 11.34 |
| travel_hours | 6.49 | 7.41 | 7.13 |
| idle_hours | 0.1 | 0.37 | 0.4 |
| refuel_stops | 0 | 0 | 0 |
| invariant_violations | 0 | 0 | 0 |

vs FCFS: wins 44 · ties 5 · losses 1

vs EDF: wins 26 · ties 17 · losses 7

vs EDF, priority-weighted: wins 40 · ties 4 · losses 6

Demo scenario (T1 breaks down at 08:00):

| metric | coordinator | EDF | FCFS |
|---|---|---|---|
| jobs_completed | 8 | 7 | 7 |
| priority1_completed | 3 | 2 | 1 |
| priority_score | 21.0 | 16.0 | 14.0 |
| travel_hours | 11.47 | 9.0 | 10.66 |
| idle_hours | 0.08 | 1.5 | 0.29 |
| refuel_stops | 1 | 0 | 1 |
| invariant_violations | 0 | 0 | 0 |
