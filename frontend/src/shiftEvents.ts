import type { LogEntry } from './types'

type Trigger = Record<string, string | number>

export interface ShiftEvent {
  index: number
  time: number
  trigger: Trigger
  /** What the event did to the plan, or undefined while the re-plan is not in the log yet. */
  outcome?: string
  isUnprompted: boolean
}

const plural = (n: number, word: string): string => `${n} ${word}${n === 1 ? '' : 's'}`

/** What the re-plan that followed an event did, in one line. */
function outcomeOf(replan: LogEntry | undefined): string | undefined {
  const changes = replan?.data.diff?.changes
  if (!replan || !changes) return undefined
  if (replan.data.accepted === false) return 'The new plan was vetoed; the last valid plan stays.'
  const moved = changes.filter((c) => c.after.startsWith('T'))
  const lost = changes.filter((c) => c.after === 'unassignable')
  if (!moved.length && !lost.length) return 'The plan did not have to change.'
  const parts = [
    ...(moved.length ? [`${plural(moved.length, 'job')} moved to another tractor (${moved.map((c) => `${c.job_id} → ${c.after}`).join(', ')})`] : []),
    ...(lost.length ? [`${plural(lost.length, 'job')} can no longer be done (${lost.map((c) => c.job_id).join(', ')})`] : []),
  ]
  return `${parts.join('; ')}.`
}

/** Every event of the shift so far, each paired with the re-plan it caused. */
export function shiftEvents(log: LogEntry[]): ShiftEvent[] {
  return log.flatMap((entry, i) => {
    if (entry.kind !== 'event') return []
    const next = log[i + 1]
    const replan = next?.kind === 'replan' ? next : undefined
    const trigger = { ...(entry.data as Trigger), ...(replan?.data.diff?.trigger ?? {}) }
    const source = trigger.source
    return [{ index: entry.index, time: entry.time, trigger, outcome: outcomeOf(replan), isUnprompted: source === 'surprise' || source === 'telemetry' }]
  })
}
