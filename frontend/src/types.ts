export type TractorStatus = 'idle' | 'traveling' | 'working' | 'refueling' | 'broken'
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

export interface ReplanData {
  duration_ms: number
  accepted: boolean
  invariants: { checked: string[]; violations: string[] }
  diff: { trigger: Record<string, string | number>; time: number; changes: JobChange[] }
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
}

export interface SessionView {
  running: boolean
  speed: number
  scenario: string
  runs: Record<Strategy, RunSnapshot>
  explanations: Record<string, Explanation>
}

export interface MapInfo {
  depot: { id: string; x: number; y: number }
  fields: { id: string; x: number; y: number }[]
  speeds: number[]
  shift_start_hour: number
}

export interface ProposedEvent {
  type: 'breakdown' | 'block_road' | 'change_priority'
  tractor_id?: string
  a?: string
  b?: string
  job_id?: string
  priority?: number
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
