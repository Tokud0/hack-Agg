import { useEffect, useRef, useState } from 'react'
import { describeTrigger } from './labels'
import type { AgentMessage, Explanation, LogEntry } from './types'

/** A re-plan's whole conversation is spread over about this long, so a person can follow it. */
const PLAYBACK_MS = 3500
const MIN_STEP_MS = 45
const MAX_STEP_MS = 170
/** How long the latest message stays on the map after it appears. */
const SPEECH_MS = 2600

export interface RadioItem {
  id: string
  time: number
  /** A message between agents, or (when absent) a divider that opens a re-plan. */
  message?: AgentMessage
  title?: string
  note?: string
}

export interface Speech {
  id: string
  message: AgentMessage
}

const STATUS_TEXT: Record<string, (job: string) => string> = {
  job_started: (job) => `Started ${job}.`,
  job_done: (job) => `Finished ${job}.`,
  refuel_started: (job) => `Refuelling at the depot before ${job}.`,
  refueled: (job) => `Tank is full, heading to ${job}.`,
}

/** What one log entry sounds like on the radio. */
function itemsOf(entry: LogEntry): RadioItem[] {
  const say = STATUS_TEXT[entry.kind]
  const tractorId = entry.data.tractor_id
  if (say && typeof tractorId === 'string') {
    const job = String(entry.data.job_id ?? '')
    const message: AgentMessage = { sender: tractorId, to: 'all', kind: 'status', phase: 'situation', text: say(job), topic: job, data: {} }
    return [{ id: `log-${entry.index}`, time: entry.time, message }]
  }
  if (entry.kind !== 'replan' || !entry.data.messages?.length) return []
  const took = entry.data.duration_ms === undefined ? '' : `decided in ${entry.data.duration_ms.toFixed(1)} ms, `
  return [
    { id: `replan-${entry.index}`, time: entry.time, title: `Re-plan: ${describeTrigger(entry.data.diff?.trigger ?? {})}`, note: `${took}played back slowed down` },
    ...entry.data.messages.map((message, i) => ({ id: `replan-${entry.index}-${i}`, time: entry.time, message })),
  ]
}

function explainerItem(index: string, time: number, explanation: Explanation): RadioItem {
  const message: AgentMessage = {
    sender: 'explainer', to: 'operator', kind: 'explain', phase: 'approval', topic: '', data: {},
    text: `${explanation.headline}. ${explanation.summary}`,
  }
  return { id: `explain-${index}`, time, message }
}

interface Seen {
  logIndex: number
  replanTimes: Map<string, number>
  explained: Set<string>
  hasSynced: boolean
  sessionId?: string
}

const freshSeen = (): Seen => ({ logIndex: -1, replanTimes: new Map(), explained: new Set(), hasSynced: false })

/**
 * The agents' live radio: status calls as the simulator reports them, and each re-plan's recorded
 * conversation revealed one message at a time. The plan itself is decided in milliseconds; the
 * pacing here is only for the reader.
 */
export function useAgentRadio(
  log: LogEntry[] | undefined,
  explanations: Record<string, Explanation> | undefined,
  now: number,
  sessionId: string | undefined,
): { items: RadioItem[]; backlog: number; speech: Speech | null } {
  const [feed, setFeed] = useState<RadioItem[]>([])
  const [shown, setShown] = useState(0)
  const [speech, setSpeech] = useState<Speech | null>(null)
  const seen = useRef<Seen>(freshSeen())

  // Append what is new. The feed only ever grows, so the playback position stays valid.
  useEffect(() => {
    if (!log) return
    const newest = log.at(-1)?.index ?? -1
    const isRestart = seen.current.hasSynced && sessionId !== seen.current.sessionId
    if (isRestart) seen.current = { ...freshSeen(), hasSynced: true }
    seen.current.sessionId = sessionId

    const fresh: RadioItem[] = []
    for (const entry of log) {
      if (entry.index <= seen.current.logIndex) continue
      fresh.push(...itemsOf(entry))
      if (entry.kind === 'replan') seen.current.replanTimes.set(String(entry.index), entry.time)
    }
    seen.current.logIndex = Math.max(seen.current.logIndex, newest)
    for (const [index, explanation] of Object.entries(explanations ?? {})) {
      const time = seen.current.replanTimes.get(index)
      if (time === undefined || seen.current.explained.has(index)) continue
      seen.current.explained.add(index)
      fresh.push(explainerItem(index, time, explanation))
    }

    // Opening the page mid-shift shows the history at once instead of replaying all of it.
    const isCatchingUp = !seen.current.hasSynced && now > 0
    seen.current.hasSynced = true
    if (isRestart) {
      setFeed(fresh)
      setShown(0)
    } else if (fresh.length) {
      setFeed((items) => [...items, ...fresh])
      if (isCatchingUp) setShown((count) => count + fresh.length)
    }
  }, [log, explanations, sessionId]) // eslint-disable-line react-hooks/exhaustive-deps -- `now` is read, not watched

  // Reveal the backlog one message at a time.
  const backlog = Math.max(0, feed.length - shown)
  useEffect(() => {
    if (backlog === 0) return
    const step = Math.max(MIN_STEP_MS, Math.min(MAX_STEP_MS, PLAYBACK_MS / backlog))
    const timer = window.setTimeout(() => setShown((count) => count + 1), step)
    return () => window.clearTimeout(timer)
  }, [backlog, shown])

  // The newest revealed message is what the map shows as "speaking".
  const latest = feed[shown - 1]
  useEffect(() => {
    if (!latest?.message) return
    setSpeech({ id: latest.id, message: latest.message })
    const timer = window.setTimeout(() => setSpeech(null), SPEECH_MS)
    return () => window.clearTimeout(timer)
  }, [latest])

  return { items: feed.slice(0, shown), backlog, speech }
}
