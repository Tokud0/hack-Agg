export type TractorStatus = 'idle' | 'traveling' | 'working' | 'refueling' | 'waiting' | 'broken'
export type JobStatus = 'pending' | 'assigned' | 'in_progress' | 'done' | 'unassignable'
export type Strategy = 'baseline' | 'edf' | 'coordinator'

export interface Tractor {
  id: string
  implement: 'sprayer' | 'mower'
  status: TractorStatus
  x: number
  y: number
  node: string
  fuel: number
  fuel_capacity: number
  current_job: string | null
  queue: string[]
  path: string[]
  refuels: number
  refuel_stop: boolean
}

export interface Job {
  id: string
  type: 'spray' | 'mow'
  field_id: string
  priority: number
  deadline: number
  work_hours: number
  progress: number
  status: JobStatus
  tractor_id: string | null
  reason: string | null
  completed_at: number | null
  /** When the current plan finishes this job, and the spare time before its deadline; null when it is not planned. */
  /** Weather hold: no work on this job before this time (hours since shift start); 0 when there is none. */
  not_before: number
  projected_finish: number | null
  slack: number | null
  at_risk: boolean
}

export interface GanttBlock {
  tractor_id: string
  job_id: string
  start: number
  end: number
  kind: 'done' | 'interrupted' | 'active' | 'planned' | 'refuel'
}

export interface Metrics {
  jobs_total: number
  jobs_completed: number
  priority1_completed: number
  priority_score: number
  refuel_stops: number
  travel_hours: number
  travel_per_job: number
  idle_hours: number
  unassignable: number
  invariant_violations: number
  replans: number
  makespan_hours: number
}

export interface JobChange {
  job_id: string
  field_id: string
  job_type: string
  priority: number
  before: string
  after: string
  reason: string | null
  progress: number
}

export interface PlanCandidate {
  name: string
  start_score: number | null
  score: number | null
  jobs_assigned: number
  is_winner: boolean
}

/** A kind of work the weather rules out until a given time (hours since shift start). */
export interface WeatherHold {
  job_type: 'spray' | 'mow'
  until: number
}

/** What each stage of the re-plan pipeline saw and produced. */
export interface ReplanTrace {
  sense: { open_jobs: string[]; tractors_available: string[]; released: string[]; blocked_roads: number }
  agronomy: { holds: WeatherHold[] }
  navigate: { locations: number; roads_closed: string[][] }
  plan: { duration_ms: number; score: number; candidates: PlanCandidate[] }
  verify: { duration_ms: number; accepted: boolean }
  dispatch: { jobs_changed: number; unassignable: string[] }
}

export type MessagePhase = 'situation' | 'auction' | 'negotiation' | 'approval'

/** One message between agents during a re-plan. Sender and receiver are a tractor id, "fleet_agent", "navigation_agent", "safety_agent" or "all". */
export interface AgentMessage {
  sender: string
  to: string
  kind: string
  phase: MessagePhase
  text: string
  topic: string
  data: { is_winner?: boolean; accepted?: boolean } & Record<string, unknown>
}

export interface ReplanData {
  duration_ms: number
  accepted: boolean
  invariants: { checked: string[]; violations: string[]; warnings?: string[] }
  diff: { trigger: Record<string, string | number>; time: number; changes: JobChange[] }
  trace: ReplanTrace
  messages: AgentMessage[]
}

export interface FaultTestResult {
  fault: string
  accepted: boolean
  checked: string[]
  violations: string[]
}

export interface LogEntry {
  index: number
  time: number
  kind: string
  message: string
  data: Partial<ReplanData> & Record<string, unknown>
}

export interface RunSnapshot {
  strategy: Strategy
  time: number
  tractors: Tractor[]
  jobs: Job[]
  blocked_roads: string[][]
  gantt: GanttBlock[]
  metrics: Metrics
  log: LogEntry[]
}

export interface Explanation {
  headline: string
  summary: string
  highlight_jobs: string[]
  source: string
  latency_ms?: number
}

export interface SessionView {
  /** Changes whenever a new shift starts (restart or new scenario). */
  session_id: string
  running: boolean
  speed: number
  scenario: string
  runs: Record<Strategy, RunSnapshot>
  explanations: Record<string, Explanation>
  /** Faults that will arrive by themselves on the simulation clock. */
  scheduled_faults: { tractor_id: string; at: number }[]
  /** Generated events of a random shift that have not happened yet. */
  surprises_left: number
  weather_holds: WeatherHold[]
}

export interface MapInfo {
  depot: { id: string; x: number; y: number }
  fields: { id: string; x: number; y: number }[]
  speeds: number[]
  shift_start_hour: number
}

export interface ProposedEvent {
  type: 'breakdown' | 'block_road' | 'change_priority' | 'weather'
  tractor_id?: string
  a?: string
  b?: string
  job_id?: string
  priority?: number
  /** Weather: the work it rules out and for how many hours from now. */
  job_type?: 'spray' | 'mow'
  hours?: number
  /** Who raised it; the copilot's proposals are tagged so the trace can show it. */
  source?: 'operator' | 'copilot' | 'telemetry'
}

export interface WhyFacts {
  job_id: string
  field_id: string
  type: string
  priority: number
  priority_weight: number
  deadline: number
  status: JobStatus
  tractor_id: string | null
  reason?: string | null
  queue_position?: number
  travel_hours_to_field?: number
  planned_finish?: number
  deadline_slack_hours?: number
  fuel_before?: number
  fuel_after?: number
  fuel_capacity?: number
  alternatives: { tractor_id: string; feasible: boolean; reason: string; added_cost?: number }[]
}

export interface JobDraft {
  type: 'spray' | 'mow'
  field_id: string
  priority: number
  deadline_hours: number
  work_hours: number
}

export interface ForecastMetrics {
  jobs_completed: number
  priority1_completed: number
  travel_hours: number
  idle_hours: number
}

export interface WhatIfResult {
  facts: {
    event: ProposedEvent
    at_hours: number
    current: ForecastMetrics
    what_if: ForecastMetrics
    lost_jobs: { job_id: string; reason: string }[]
    gained_jobs: string[]
  }
  headline: string
  answer: string
  source: string
}

export interface AttentionItem {
  kind: 'broken' | 'lost' | 'at_risk' | 'low_fuel'
  id: string
  text: string
}

export interface ShiftBriefing {
  headline: string
  summary: string
  source: string
  clock: string
  jobs: { total: number; done_on_time: number; in_progress: number; waiting: number; not_doable: number }
  attention: AttentionItem[]
}
