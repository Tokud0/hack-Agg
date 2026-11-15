import { AnimatePresence, animate, motion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'
import type { Explanation, LogEntry, Metrics, ReplanData } from '../types'
import { clock } from '../theme'
import { ShieldIcon, SparkIcon } from './Icons'

/* ---------- animated number ---------- */

export function AnimatedNumber({ value, decimals = 0 }: { value: number; decimals?: number }) {
  const ref = useRef<HTMLSpanElement>(null)
  const previous = useRef(value)
  useEffect(() => {
    const controls = animate(previous.current, value, {
      duration: 0.6,
      onUpdate: (v) => {
        if (ref.current) ref.current.textContent = v.toFixed(decimals)
      },
    })
    previous.current = value
    return () => controls.stop()
  }, [value, decimals])
  return <span ref={ref}>{value.toFixed(decimals)}</span>
}

/* ---------- counters strip ---------- */

interface CountersProps {
  metrics: Metrics
  accent: string
  /** When given, shows how far ahead of this run we are. */
  compareTo?: Metrics
}

type CounterKey = 'jobs_completed' | 'priority1_completed' | 'travel_hours' | 'idle_hours'

const COUNTERS: { key: CounterKey; label: string; suffix: string; decimals: number; higherIsBetter: boolean }[] = [
  { key: 'jobs_completed', label: 'Done on time', suffix: '', decimals: 0, higherIsBetter: true },
  { key: 'priority1_completed', label: 'Urgent (P1) done', suffix: '', decimals: 0, higherIsBetter: true },
  { key: 'travel_hours', label: 'Driving', suffix: 'h', decimals: 1, higherIsBetter: false },
  { key: 'idle_hours', label: 'Standing idle', suffix: 'h', decimals: 1, higherIsBetter: false },
]

function Delta({ value, decimals, higherIsBetter }: { value: number; decimals: number; higherIsBetter: boolean }) {
  if (Math.abs(value) < 10 ** -decimals / 2) return null
  const good = higherIsBetter ? value > 0 : value < 0
  return (
    <motion.span key={value.toFixed(decimals)} initial={{ scale: 1.3 }} animate={{ scale: 1 }}
      className={`ml-1 rounded px-1 text-[10px] font-bold ${good ? 'bg-leaf/15 text-leaf' : 'bg-alarm/15 text-alarm'}`}>
      {value > 0 ? '+' : ''}{value.toFixed(decimals)}
    </motion.span>
  )
}

export function Counters({ metrics, accent, compareTo }: CountersProps) {
  const items = COUNTERS.map((c) => ({
    ...c,
    value: metrics[c.key],
    suffix: c.key === 'jobs_completed' ? `/${metrics.jobs_total}` : c.suffix,
    delta: compareTo ? metrics[c.key] - compareTo[c.key] : 0,
  }))
  return (
    <div className="grid grid-cols-4 gap-2">
      {items.map((it) => (
        <div key={it.label} className="rounded-lg bg-black/25 px-2.5 py-1.5">
          <div className="text-[10px] uppercase tracking-wider text-white/45">{it.label}</div>
          <div className="font-mono text-lg font-bold" style={{ color: accent }}>
            <AnimatedNumber value={it.value} decimals={it.decimals} />
            <span className="text-xs text-white/40">{it.suffix}</span>
            {compareTo && <Delta value={it.delta} decimals={it.decimals} higherIsBetter={it.higherIsBetter} />}
          </div>
        </div>
      ))}
    </div>
  )
}

/* ---------- invariant checks ---------- */

const INVARIANT_LABELS: Record<string, string> = {
  one_tractor_per_job: 'Each job has at most one tractor',
  done_never_reassigned: 'Completed work never reassigned',
  hard_constraints: 'Implement · fuel · deadline respected',
  every_open_job_accounted: 'No work lost: reassigned or flagged',
}

export function InvariantPanel({ replan, entryIndex }: { replan?: Partial<ReplanData>; entryIndex: number }) {
  const checked = replan?.invariants?.checked ?? Object.keys(INVARIANT_LABELS)
  const violations = replan?.invariants?.violations ?? []
  return (
    <div className="panel p-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-widest text-white/60"><ShieldIcon size={14} className="text-leaf" />Safety checks</h3>
        {replan?.duration_ms !== undefined && (
          <motion.span key={entryIndex} initial={{ scale: 1.4, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}
            className="rounded-full bg-leaf/15 px-2 py-0.5 font-mono text-[11px] text-leaf">
            re-planned in {replan.duration_ms.toFixed(1)} ms
          </motion.span>
        )}
      </div>
      <ul className="space-y-1.5">
        {checked.map((name, i) => {
          const failed = violations.some((v) => v.startsWith(name))
          return (
            <motion.li key={`${entryIndex}-${name}`} className="flex items-center gap-2 text-[13px]"
              initial={{ opacity: 0.25, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.25 + i * 0.22 }}>
              <motion.span className={`grid h-5 w-5 place-items-center rounded-full text-[11px] font-bold ${failed ? 'bg-alarm text-black' : 'bg-leaf text-black'}`}
                initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: 0.25 + i * 0.22, type: 'spring' }}>
                {failed ? '✕' : '✓'}
              </motion.span>
              <span className="text-white/85">{INVARIANT_LABELS[name] ?? name}</span>
            </motion.li>
          )
        })}
      </ul>
      <div className={`mt-2 text-right font-mono text-xs ${violations.length ? 'text-alarm' : 'text-leaf'}`}>
        {violations.length} violations
      </div>
    </div>
  )
}

/* ---------- explanation card with typewriter ---------- */

const TYPE_MS = 14

function useTypewriter(text: string): string {
  const [shown, setShown] = useState('')
  useEffect(() => {
    let i = 0
    setShown('')
    const id = window.setInterval(() => {
      i += 2
      setShown(text.slice(0, i))
      if (i >= text.length) window.clearInterval(id)
    }, TYPE_MS)
    return () => window.clearInterval(id)
  }, [text])
  return shown
}

interface ExplanationCardProps {
  explanation?: Explanation
  pending: boolean
  onHover: (jobs: string[]) => void
}

export function ExplanationCard({ explanation, pending, onHover }: ExplanationCardProps) {
  const typed = useTypewriter(explanation?.summary ?? '')
  return (
    <div className="panel relative overflow-hidden p-4" onMouseEnter={() => onHover(explanation?.highlight_jobs ?? [])}
      onMouseLeave={() => onHover([])}>
      <div className="absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-wheat via-leaf to-transparent" />
      <div className="mb-1 flex items-center justify-between">
        <h3 className="text-xs font-bold uppercase tracking-widest text-white/60">What changed & why</h3>
        {explanation && (
          <SourceBadge source={explanation.source} />
        )}
      </div>
      <AnimatePresence mode="wait">
        {pending && !explanation ? (
          <motion.div key="pending" className="flex items-center gap-2 py-3 text-sm text-white/50" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <span className="blink">●</span> AI is reading the plan change…
          </motion.div>
        ) : explanation ? (
          <motion.div key={explanation.summary} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
            <div className="text-lg font-bold leading-tight text-white">{explanation.headline}</div>
            <p className="mt-1 min-h-[3.5rem] text-[13.5px] leading-relaxed text-white/80">{typed}</p>
            <div className="mt-2 flex flex-wrap gap-1">
              {explanation.highlight_jobs.map((j) => (
                <span key={j} className="rounded border border-wheat/30 bg-wheat/10 px-1.5 font-mono text-[11px] text-wheat">{j}</span>
              ))}
            </div>
          </motion.div>
        ) : (
          <div className="py-3 text-sm text-white/40">Waiting for the first plan…</div>
        )}
      </AnimatePresence>
    </div>
  )
}

/* ---------- AI source badge ---------- */

const SOURCE_LABEL: Record<string, string> = { groq: 'AI · Groq', claude: 'AI · Claude', template: 'rule-based' }

export function SourceBadge({ source }: { source: string }) {
  const isAi = source !== 'template'
  return (
    <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold ${isAi ? 'bg-wheat/20 text-wheat' : 'bg-white/10 text-white/50'}`}>
      {isAi && <SparkIcon size={10} />}{SOURCE_LABEL[source] ?? source}
    </span>
  )
}

/* ---------- event log ---------- */

const KIND_STYLE: Record<string, string> = {
  replan: 'text-leaf',
  event: 'text-alarm',
  job_done: 'text-white/70',
  job_started: 'text-white/45',
  start: 'text-wheat',
}

export function EventLog({ log }: { log: LogEntry[] }) {
  const ordered = [...log].reverse().slice(0, 60)
  return (
    <div className="h-full overflow-y-auto pr-1 font-mono text-[11.5px]">
      <AnimatePresence initial={false}>
        {ordered.map((e) => (
          <motion.div key={e.index} layout initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }}
            className="flex gap-2 border-b border-white/5 py-1">
            <span className="text-white/35">{clock(e.time)}</span>
            <span className={KIND_STYLE[e.kind] ?? 'text-white/60'}>{e.message}</span>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}
