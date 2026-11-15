import { useEffect, useRef, useState } from 'react'
import type { Scenario, Trouble } from './scenario'
import type { IncidentRecord, ShiftBriefing } from './types'
import type { FaultTestResult, JobDraft, MapInfo, ProposedEvent, SessionView, WhatIfResult, WhyFacts } from './types'

const RECONNECT_MS = 1000

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? `Request failed (${res.status})`)
  }
  return res.json() as Promise<T>
}

export const api = {
  map: () => request<MapInfo>('/api/map'),
  health: () => request<{ ok: boolean; llm: boolean; provider: string }>('/api/health'),
  control: (action: 'play' | 'pause' | 'reset' | 'speed', speed?: number) =>
    request('/api/control', { method: 'POST', body: JSON.stringify({ action, speed }) }),
  event: (event: ProposedEvent) => request('/api/events', { method: 'POST', body: JSON.stringify(event) }),
  why: (jobId: string, question?: string) =>
    request<{ facts: WhyFacts; answer: string; source: string }>(
      `/api/why/${jobId}${question ? `?question=${encodeURIComponent(question)}` : ''}`,
    ),
  copilot: (message: string, history: { role: 'operator' | 'copilot'; text: string }[]) =>
    request<{ reply: string; events: ProposedEvent[]; source: string }>('/api/copilot', {
      method: 'POST',
      body: JSON.stringify({ message, history }),
    }),
  addJob: (job: { type: string; field_id: string; priority: number; deadline: number; work_hours: number }) =>
    request<{ ok: boolean; job_id: string }>('/api/jobs', { method: 'POST', body: JSON.stringify(job) }),
  parseJobs: (text: string) =>
    request<{ jobs: JobDraft[]; note: string; source: string }>('/api/jobs/parse', {
      method: 'POST',
      body: JSON.stringify({ text }),
    }),
  whatIf: (event: ProposedEvent) => request<WhatIfResult>('/api/whatif', { method: 'POST', body: JSON.stringify(event) }),
  currentScenario: () => request<Scenario>('/api/scenario'),
  /** A generated shift. The same seed and trouble level always give the same shift and the same events. */
  randomScenario: (trouble: Trouble, seed?: number) =>
    request<Scenario>(`/api/scenario/random?trouble=${trouble}${seed === undefined ? '' : `&seed=${seed}`}`),
  describeScenario: (text: string) =>
    request<{ scenario: Scenario; source: string; changes: string[] }>('/api/scenario/describe', { method: 'POST', body: JSON.stringify({ text }) }),
  checkScenario: (scenario: Scenario) =>
    request<{ impossible: Record<string, string>; fixed: Scenario | null; changes: string[] }>('/api/scenario/check', {
      method: 'POST',
      body: JSON.stringify(scenario),
    }),
  uploadScenario: (scenario: unknown) =>
    request<{ ok: boolean; scenario: string; jobs: number }>('/api/scenario', { method: 'POST', body: JSON.stringify(scenario) }),
  askAgent: (tractorId: string, question: string, replanIndex: number) =>
    request<{ answer: string; source: string }>(`/api/agents/${tractorId}/ask`, {
      method: 'POST',
      body: JSON.stringify({ question, replan_index: replanIndex }),
    }),
  scheduleFault: (tractorId: string, delayHours: number) =>
    request<{ ok: boolean; at: number }>('/api/events/schedule', {
      method: 'POST',
      body: JSON.stringify({ tractor_id: tractorId, delay_hours: delayHours }),
    }),
  investigateIncident: (replanIndex: number) => request<IncidentRecord>(`/api/incidents/${replanIndex}/investigate`, { method: 'POST' }),
  briefing: () => request<ShiftBriefing>('/api/briefing'),
  faultTest: () => request<FaultTestResult>('/api/orchestration/fault-test', { method: 'POST' }),
  benchmark: () => request<BenchmarkResult>('/api/benchmark'),
}

export interface Versus {
  wins: number
  ties: number
  losses: number
}

export interface BenchmarkResult extends Versus {
  n: number
  vs_edf: Versus
  vs_edf_priority: Versus
  summary: Record<'coordinator' | 'baseline' | 'edf', Record<string, number>>
}

/** Live session state streamed over WebSocket, auto-reconnecting. */
export function useLiveState(): { view: SessionView | null; connected: boolean } {
  const [view, setView] = useState<SessionView | null>(null)
  const [connected, setConnected] = useState(false)
  const socketRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let cancelled = false
    let timer: number | undefined

    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(`${proto}://${location.host}/api/ws`)
      socketRef.current = ws
      ws.onopen = () => setConnected(true)
      ws.onmessage = (msg) => setView(JSON.parse(msg.data) as SessionView)
      ws.onclose = () => {
        setConnected(false)
        if (!cancelled) timer = window.setTimeout(connect, RECONNECT_MS)
      }
      ws.onerror = () => ws.close()
    }
    connect()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
      socketRef.current?.close()
    }
  }, [])

  return { view, connected }
}
