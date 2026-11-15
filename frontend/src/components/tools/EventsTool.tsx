import { AnimatePresence, motion } from 'framer-motion'
import { useState } from 'react'
import { api } from '../../api'
import type { Job, ProposedEvent, Tractor, WhatIfResult } from '../../types'
import { clock } from '../../theme'
import { BoltIcon, SparkIcon } from '../Icons'
import { SourceBadge } from '../Panels'
import { describeEvent, errorText, inputCls } from './shared'

type Kind = ProposedEvent['type']

interface EventsToolProps {
  tractors: Tractor[]
  jobs: Job[]
  nodes: string[]
  scheduledFaults: { tractor_id: string; at: number }[]
}

const KIND_LABEL: Record<Kind, string> = {
  breakdown: 'Tractor breaks down',
  block_road: 'Road closes',
  change_priority: 'Priority changes',
}

function CompareBar({ label, now, alt, max, higherIsBetter }: { label: string; now: number; alt: number; max: number; higherIsBetter: boolean }) {
  const worse = higherIsBetter ? alt < now : alt > now
  return (
    <div>
      <div className="flex justify-between text-[11px]"><span className="text-white/60">{label}</span>
        <span className="font-mono">{now} → <b className={worse ? 'text-alarm' : 'text-leaf'}>{alt}</b></span></div>
      <div className="mt-1 space-y-0.5">
        <motion.div className="h-1.5 rounded-full bg-white/30" initial={{ width: 0 }} animate={{ width: `${(now / max) * 100}%` }} />
        <motion.div className={`h-1.5 rounded-full ${worse ? 'bg-alarm' : 'bg-leaf'}`} initial={{ width: 0 }}
          animate={{ width: `${(alt / max) * 100}%` }} transition={{ delay: 0.2 }} />
      </div>
    </div>
  )
}

function ForecastCard({ result }: { result: WhatIfResult }) {
  const { current, what_if: alt, lost_jobs: lost } = result.facts
  const maxJobs = Math.max(current.jobs_completed, alt.jobs_completed, 1)
  const maxHours = Math.max(current.travel_hours, alt.travel_hours, current.idle_hours, alt.idle_hours, 1)
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="rounded-lg border border-sky-300/25 bg-sky-300/5 p-3">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest text-sky-300">Forecast for the rest of the shift</span>
        <SourceBadge source={result.source} />
      </div>
      <div className="mt-1 text-base font-bold">{result.headline}</div>
      <p className="mt-1 text-[12.5px] leading-relaxed text-white/75">{result.answer}</p>
      <div className="mt-3 space-y-2">
        <CompareBar label="Jobs done on time" now={current.jobs_completed} alt={alt.jobs_completed} max={maxJobs} higherIsBetter />
        <CompareBar label="Urgent (P1) done" now={current.priority1_completed} alt={alt.priority1_completed} max={maxJobs} higherIsBetter />
        <CompareBar label="Idle hours" now={current.idle_hours} alt={alt.idle_hours} max={maxHours} higherIsBetter={false} />
      </div>
      <div className="mt-2 text-[10px] text-white/35">grey: as planned now · colour: if it happens</div>
      {lost.length > 0 && (
        <ul className="mt-2 space-y-1">
          {lost.map((l) => (
            <li key={l.job_id} className="text-[11.5px]"><b className="text-alarm">{l.job_id} lost</b> <span className="text-white/55">{l.reason}</span></li>
          ))}
        </ul>
      )}
    </motion.div>
  )
}

const FAULT_DELAYS = [
  { hours: 0.5, label: '30 min' },
  { hours: 1, label: '1 h' },
  { hours: 2, label: '2 h' },
]

export function EventsTool({ tractors, jobs, nodes, scheduledFaults }: EventsToolProps) {
  const healthy = tractors.filter((t) => t.status !== 'broken')
  const openJobs = jobs.filter((j) => j.status !== 'done')
  const [kind, setKind] = useState<Kind>('breakdown')
  const [tractorId, setTractorId] = useState(healthy[0]?.id ?? '')
  const [roadA, setRoadA] = useState(nodes[1] ?? '')
  const [roadB, setRoadB] = useState(nodes[2] ?? '')
  const [jobId, setJobId] = useState(openJobs[0]?.id ?? '')
  const [priority, setPriority] = useState(1)
  const [forecast, setForecast] = useState<WhatIfResult | null>(null)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const [isBusy, setIsBusy] = useState(false)

  const event: ProposedEvent =
    kind === 'breakdown' ? { type: kind, tractor_id: tractorId }
      : kind === 'block_road' ? { type: kind, a: roadA, b: roadB }
        : { type: kind, job_id: jobId, priority }

  const runForecast = async () => {
    setIsBusy(true)
    setMessage(null)
    try {
      setForecast(await api.whatIf(event))
    } catch (err) {
      setMessage({ ok: false, text: errorText(err) })
    } finally {
      setIsBusy(false)
    }
  }

  const applyNow = async () => {
    setIsBusy(true)
    try {
      await api.event(event)
      setForecast(null)
      setMessage({ ok: true, text: `${describeEvent(event)}. The coordinator re-planned.` })
    } catch (err) {
      setMessage({ ok: false, text: errorText(err) })
    } finally {
      setIsBusy(false)
    }
  }

  const schedule = async (delayHours: number) => {
    setIsBusy(true)
    try {
      const res = await api.scheduleFault(tractorId, delayHours)
      setMessage({ ok: true, text: `Scheduled: ${tractorId} fails at ${clock(res.at)} without any click.` })
    } catch (err) {
      setMessage({ ok: false, text: errorText(err) })
    } finally {
      setIsBusy(false)
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto pr-1 text-[13px]">
      <p className="text-[12px] text-white/50">Pick a disruption. <b className="text-white/75">Forecast</b> simulates the rest of the shift without touching the live plan. <b className="text-white/75">Apply now</b> makes it happen.</p>
      <div className="grid grid-cols-3 gap-1">
        {(Object.keys(KIND_LABEL) as Kind[]).map((k) => (
          <button type="button" key={k} onClick={() => { setKind(k); setForecast(null) }}
            className={`rounded-md px-2 py-1.5 text-[11.5px] font-semibold ${kind === k ? 'bg-white/15 text-white' : 'bg-white/5 text-white/50 hover:bg-white/10'}`}>
            {KIND_LABEL[k]}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {kind === 'breakdown' && (
          <select aria-label="tractor" className={inputCls} value={tractorId} onChange={(e) => setTractorId(e.target.value)}>
            {healthy.map((t) => <option key={t.id} value={t.id}>{t.id} ({t.implement})</option>)}
          </select>
        )}
        {kind === 'block_road' && (
          <>
            <select aria-label="from" className={inputCls} value={roadA} onChange={(e) => setRoadA(e.target.value)}>{nodes.map((n) => <option key={n}>{n}</option>)}</select>
            <span className="text-white/40">to</span>
            <select aria-label="to" className={inputCls} value={roadB} onChange={(e) => setRoadB(e.target.value)}>{nodes.map((n) => <option key={n}>{n}</option>)}</select>
          </>
        )}
        {kind === 'change_priority' && (
          <>
            <select aria-label="job" className={inputCls} value={jobId} onChange={(e) => setJobId(e.target.value)}>
              {openJobs.map((j) => <option key={j.id} value={j.id}>{j.id} · {j.field_id} · P{j.priority} · due {clock(j.deadline)}</option>)}
            </select>
            <select aria-label="new priority" className={inputCls} value={priority} onChange={(e) => setPriority(Number(e.target.value))}>
              {[1, 2, 3].map((p) => <option key={p} value={p}>P{p}</option>)}
            </select>
          </>
        )}
      </div>

      <div className="flex gap-2">
        <button type="button" onClick={runForecast} disabled={isBusy}
          className="flex flex-1 items-center justify-center gap-1.5 rounded-md bg-sky-300 py-1.5 text-xs font-bold text-black disabled:opacity-40">
          <SparkIcon size={12} />Forecast (what if)
        </button>
        <button type="button" onClick={applyNow} disabled={isBusy}
          className="flex flex-1 items-center justify-center gap-1.5 rounded-md bg-alarm py-1.5 text-xs font-bold text-black disabled:opacity-40">
          <BoltIcon size={12} />Apply now
        </button>
      </div>

      {kind === 'breakdown' && (
        <div className="rounded-lg border border-white/8 bg-black/20 p-2.5">
          <div className="text-[12px] font-bold text-white/85">Hands-off test</div>
          <p className="mt-0.5 text-[11.5px] leading-snug text-white/50">Let the fault arrive by itself, as the tractor&apos;s telemetry would report it. Nobody clicks when it happens; the fleet re-plans on its own.</p>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            <span className="text-[11.5px] text-white/50">{tractorId} fails in</span>
            {FAULT_DELAYS.map((d) => (
              <button type="button" key={d.hours} onClick={() => schedule(d.hours)} disabled={isBusy || !tractorId}
                className="rounded-md border border-alarm/40 px-2 py-1 text-[11.5px] font-semibold text-alarm hover:bg-alarm/15 disabled:opacity-40">{d.label}</button>
            ))}
          </div>
          {scheduledFaults.map((f) => (
            <div key={`${f.tractor_id}-${f.at}`} className="mt-1.5 flex items-center gap-1.5 text-[11.5px] text-wheat">
              <span className="blink">●</span>{f.tractor_id} will fail at {clock(f.at)}. Press Run and watch.
            </div>
          ))}
        </div>
      )}

      {isBusy && <div className="blink text-xs text-white/40">● simulating…</div>}
      {message && <div className={`rounded-md px-2.5 py-1.5 text-[12px] ${message.ok ? 'bg-leaf/10 text-leaf' : 'bg-alarm/10 text-alarm'}`}>{message.text}</div>}
      <AnimatePresence>{forecast && <ForecastCard key={JSON.stringify(forecast.facts.event)} result={forecast} />}</AnimatePresence>
    </div>
  )
}
