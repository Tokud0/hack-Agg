import { useEffect, useRef, useState } from 'react'
import type { MapInfo, ProposedEvent, SessionView, WhyFacts } from './types'

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
  health: () => request<{ ok: boolean; llm: boolean }>('/api/health'),
  control: (action: 'play' | 'pause' | 'reset' | 'speed', speed?: number) =>
    request('/api/control', { method: 'POST', body: JSON.stringify({ action, speed }) }),
  event: (event: ProposedEvent) => request('/api/events', { method: 'POST', body: JSON.stringify(event) }),
  why: (jobId: string, question?: string) =>
    request<{ facts: WhyFacts; answer: string; source: string }>(
      `/api/why/${jobId}${question ? `?question=${encodeURIComponent(question)}` : ''}`,
    ),
  copilot: (message: string) =>
    request<{ reply: string; events: ProposedEvent[]; source: string }>('/api/copilot', {
      method: 'POST',
      body: JSON.stringify({ message }),
    }),
  benchmark: () => request<BenchmarkResult>('/api/benchmark'),
}

export interface BenchmarkResult {
  n: number
  wins: number
  ties: number
  losses: number
  summary: Record<'coordinator' | 'baseline', Record<string, number>>
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
