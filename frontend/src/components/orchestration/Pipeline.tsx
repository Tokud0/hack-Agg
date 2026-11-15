import { motion } from 'framer-motion'
import type { ReactNode } from 'react'
import type { Explanation, LogEntry, ReplanTrace } from '../../types'
import { describeTrigger } from '../../labels'
import { ArrowRightIcon } from '../Icons'

type AgentKind = 'human' | 'llm' | 'search' | 'code' | 'rules'
type Tone = 'ok' | 'bad' | 'pending'

const KIND: Record<AgentKind, { label: string; cls: string }> = {
  human: { label: 'Human + LLM', cls: 'bg-white/10 text-white/70' },
  llm: { label: 'LLM', cls: 'bg-wheat/15 text-wheat' },
  search: { label: 'Deterministic search', cls: 'bg-leaf/15 text-leaf' },
  code: { label: 'Deterministic code', cls: 'bg-leaf/15 text-leaf' },
  rules: { label: 'Hard rules', cls: 'bg-sky-400/15 text-sky-300' },
}

const TONE: Record<Tone, string> = { ok: 'text-white', bad: 'text-alarm', pending: 'text-white/50' }

const STEP_DELAY_S = 0.28

interface Stage {
  name: string
  kind: AgentKind
  role: string
  result: ReactNode
  meta: string
  tone: Tone
  limit: string
}

function describeSource(trigger: Record<string, string | number>): string {
  if (trigger.type === 'initial_plan') return 'scheduled by the system'
  if (trigger.source === 'copilot') return 'proposed by the copilot, confirmed by the operator'
  return 'reported by the operator'
}

const MIN_SHOWN_MS = 0.1
const ms = (value: number): string => (value < MIN_SHOWN_MS ? `under ${MIN_SHOWN_MS} ms` : `${value.toFixed(1)} ms`)

function buildStages(entry: LogEntry, trace: ReplanTrace, explanation?: Explanation): Stage[] {
  const trigger = entry.data.diff?.trigger ?? {}
  const winner = trace.plan.candidates.find((c) => c.is_winner)
  const violations = entry.data.invariants?.violations.length ?? 0
  const checks = entry.data.invariants?.checked.length ?? 0
  const isAccepted = trace.verify.accepted
  const closed = trace.navigate.roads_closed
  const changed = trace.dispatch.jobs_changed
  return [
    {
      name: 'Intake', kind: 'human', role: 'Turns a report into a typed event',
      result: describeTrigger(trigger), meta: describeSource(trigger), tone: 'ok',
      limit: 'Can only propose. A human confirms.',
    },
    {
      name: 'Navigation Agent', kind: 'code', role: 'Plans routes and travel times between fields',
      result: closed.length ? `Detours around ${closed.map((r) => r.join('–')).join(', ')}` : 'All roads open, direct routes',
      meta: `${trace.navigate.locations} locations on the map`, tone: 'ok',
      limit: 'Owns the road map. Every bid uses its travel times.',
    },
    {
      name: 'Fleet Agent', kind: 'search', role: 'Runs the auction between the tractor agents and assigns jobs',
      result: `${trace.plan.candidates.length} auction rounds, best: ${winner?.name ?? 'nothing to assign'}`,
      meta: `${trace.sense.open_jobs.length} open jobs · ${trace.sense.tractors_available.length} tractor agents · ${ms(trace.plan.duration_ms)}`,
      tone: 'ok', limit: 'Same input, same plan. No LLM inside.',
    },
    {
      name: 'Safety Agent', kind: 'rules', role: 'Checks the plan before any tractor acts on it',
      result: isAccepted ? `Passed ${checks} of ${checks} checks` : `Vetoed: ${violations} violation${violations === 1 ? '' : 's'}`,
      meta: isAccepted ? `${changed} job${changed === 1 ? '' : 's'} changed hands · ${trace.dispatch.unassignable.length} flagged` : 'kept the last valid plan',
      tone: isAccepted ? 'ok' : 'bad', limit: 'Has a veto. A failed plan is thrown away.',
    },
    {
      name: 'Explainer', kind: 'llm', role: 'Tells the operator what changed and why',
      result: explanation ? explanation.headline : 'Writing the explanation…',
      meta: explanation ? (explanation.source === 'template' ? 'rule-based text' : `${explanation.source} · ${explanation.latency_ms ?? 0} ms`) : 'runs after the plan is approved',
      tone: explanation ? 'ok' : 'pending', limit: 'Reads the result. Cannot change the plan.',
    },
  ]
}

interface PipelineProps {
  entry: LogEntry
  trace: ReplanTrace
  explanation?: Explanation
}

/** ATC's orchestrator layer in the order an event passes through it, filled with one re-plan's results. */
export function Pipeline({ entry, trace, explanation }: PipelineProps) {
  const stages = buildStages(entry, trace, explanation)
  return (
    <ol className="grid gap-2 md:grid-cols-5" aria-label="Agent pipeline">
      {stages.map((s, i) => (
        <motion.li key={`${entry.index}-${s.name}`} className="panel relative flex flex-col p-3"
          initial={{ opacity: 0.2, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * STEP_DELAY_S }}>
          {i > 0 && (
            <span className="absolute -left-[13px] top-7 z-10 hidden h-[18px] w-[18px] place-items-center rounded-full bg-soil-700 text-white/60 md:grid">
              <ArrowRightIcon size={11} />
            </span>
          )}
          <div className="flex items-center gap-2">
            <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-white/10 font-mono text-[11px] font-bold">{i + 1}</span>
            <h3 className="text-sm font-extrabold">{s.name}</h3>
          </div>
          <span className={`mt-1.5 self-start rounded px-1.5 py-0.5 text-[10px] font-bold ${KIND[s.kind].cls}`}>{KIND[s.kind].label}</span>
          <p className="mt-1.5 text-[11.5px] leading-snug text-white/50">{s.role}</p>
          <div className={`mt-2 text-[13px] font-semibold leading-snug ${TONE[s.tone]}`}>
            {s.tone === 'pending' && <span className="blink mr-1">●</span>}{s.result}
          </div>
          <div className="mt-1 font-mono text-[10.5px] text-white/40">{s.meta}</div>
          <p className="mt-auto border-t border-white/5 pt-2 text-[10.5px] leading-snug text-white/40">{s.limit}</p>
        </motion.li>
      ))}
    </ol>
  )
}
