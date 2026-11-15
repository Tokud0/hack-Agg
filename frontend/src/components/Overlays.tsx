import { motion } from 'framer-motion'
import { useEffect, useState } from 'react'
import { Bar, BarChart, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, type BenchmarkResult } from '../api'
import type { WhyFacts } from '../types'
import { tractorColor } from '../theme'

function Backdrop({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  return (
    <motion.div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-6 backdrop-blur-sm"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
      <motion.div className="panel max-h-[90vh] w-full max-w-3xl overflow-y-auto p-6" initial={{ scale: 0.95, y: 12 }}
        animate={{ scale: 1, y: 0 }} onClick={(e) => e.stopPropagation()}>
        {children}
      </motion.div>
    </motion.div>
  )
}

/* ---------- "why?" ---------- */

function Meter({ label, value, max, color, hint }: { label: string; value: number; max: number; color: string; hint: string }) {
  const share = Math.max(0, Math.min(1, value / max))
  return (
    <div>
      <div className="flex justify-between text-xs"><span className="text-white/60">{label}</span><span className="font-mono">{hint}</span></div>
      <div className="mt-1 h-2 overflow-hidden rounded-full bg-white/10">
        <motion.div className="h-full rounded-full" style={{ background: color }} initial={{ width: 0 }} animate={{ width: `${share * 100}%` }} transition={{ duration: 0.7 }} />
      </div>
    </div>
  )
}

export function WhyDrawer({ jobId, onClose }: { jobId: string; onClose: () => void }) {
  const [data, setData] = useState<{ facts: WhyFacts; answer: string; source: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    api.why(jobId).then((d) => alive && setData(d)).catch((e: unknown) => alive && setError(e instanceof Error ? e.message : 'failed'))
    return () => { alive = false }
  }, [jobId])

  const f = data?.facts
  return (
    <Backdrop onClose={onClose}>
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs uppercase tracking-widest text-white/50">Why this assignment?</div>
          <h2 className="text-2xl font-extrabold">{jobId} {f && <span className="text-white/50">· {f.type} {f.field_id} · P{f.priority}</span>}</h2>
        </div>
        <button type="button" onClick={onClose} className="rounded-lg bg-white/10 px-3 py-1 text-sm hover:bg-white/20">Close</button>
      </div>
      {error && <div className="mt-4 text-alarm">{error}</div>}
      {!data && !error && <div className="blink mt-6 text-white/50">● asking the coordinator and Claude…</div>}
      {f && (
        <>
          <div className="mt-4 flex items-center gap-3">
            <span className="rounded-full px-3 py-1 text-sm font-bold text-black" style={{ background: f.tractor_id ? tractorColor(f.tractor_id) : '#ff5d5d' }}>
              {f.tractor_id ?? 'UNASSIGNABLE'}
            </span>
            {f.reason && <span className="text-sm text-alarm">{f.reason}</span>}
          </div>
          {f.planned_finish !== undefined && (
            <div className="mt-4 grid grid-cols-2 gap-4">
              <Meter label="Priority weight" value={f.priority_weight} max={4} color="#ff5d5d" hint={`P${f.priority} · ×${f.priority_weight}`} />
              <Meter label="Deadline slack" value={f.deadline_slack_hours ?? 0} max={f.deadline} color="#7bd88f" hint={`${f.deadline_slack_hours}h to spare`} />
              <Meter label="Fuel after this job" value={f.fuel_after ?? 0} max={f.fuel_capacity ?? 100} color="#f2c46d" hint={`${f.fuel_before} → ${f.fuel_after} / ${f.fuel_capacity}`} />
              <Meter label="Travel to field" value={f.travel_hours_to_field ?? 0} max={3} color="#5cc8ff" hint={`${f.travel_hours_to_field}h · stop #${f.queue_position}`} />
            </div>
          )}
          <div className="mt-5 rounded-xl border border-wheat/25 bg-wheat/5 p-4">
            <div className="mb-1 text-[10px] uppercase tracking-widest text-wheat">{data?.source === 'claude' ? '✦ Claude explains' : 'Explanation'}</div>
            <p className="text-[15px] leading-relaxed">{data?.answer}</p>
          </div>
          <h3 className="mt-5 text-xs font-bold uppercase tracking-widest text-white/50">Alternatives the coordinator rejected</h3>
          <ul className="mt-2 space-y-1.5">
            {f.alternatives.map((a) => (
              <li key={a.tractor_id} className="flex items-center gap-3 text-sm">
                <span className="w-8 rounded text-center font-bold text-black" style={{ background: tractorColor(a.tractor_id) }}>{a.tractor_id}</span>
                <span className={a.feasible ? 'text-wheat' : 'text-white/70'}>{a.feasible ? '◐' : '✕'} {a.reason}</span>
              </li>
            ))}
            {f.alternatives.length === 0 && <li className="text-sm text-white/40">No alternatives to compare.</li>}
          </ul>
        </>
      )}
    </Backdrop>
  )
}

/* ---------- benchmark ---------- */

const BENCH_ROWS: { key: string; label: string }[] = [
  { key: 'jobs_completed', label: 'Jobs on time' },
  { key: 'priority1_completed', label: 'P1 jobs' },
  { key: 'travel_hours', label: 'Travel h' },
  { key: 'idle_hours', label: 'Idle h' },
]

export function BenchmarkModal({ onClose }: { onClose: () => void }) {
  const [data, setData] = useState<BenchmarkResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    api.benchmark().then(setData).catch((e: unknown) => setError(e instanceof Error ? e.message : 'failed'))
  }, [])

  const chart = data ? BENCH_ROWS.map((r) => ({ name: r.label, Coordinator: data.summary.coordinator[r.key], Baseline: data.summary.baseline[r.key] })) : []
  const gain = data ? ((data.summary.coordinator.jobs_completed / data.summary.baseline.jobs_completed - 1) * 100).toFixed(0) : '0'

  return (
    <Backdrop onClose={onClose}>
      <div className="flex items-start justify-between">
        <div>
          <div className="text-xs uppercase tracking-widest text-white/50">Benchmark · {data?.n ?? 50} random scenarios · same breakdowns</div>
          <h2 className="text-2xl font-extrabold">Coordinator vs first-come-first-served</h2>
        </div>
        <button type="button" onClick={onClose} className="rounded-lg bg-white/10 px-3 py-1 text-sm hover:bg-white/20">Close</button>
      </div>
      {error && <div className="mt-4 text-alarm">{error}</div>}
      {!data && !error && <div className="blink mt-6 text-white/50">● running 100 simulations…</div>}
      {data && (
        <>
          <div className="mt-5 grid grid-cols-3 gap-3">
            {[
              { big: `+${gain}%`, small: 'more jobs finished on time', color: 'text-leaf' },
              { big: `${data.wins}/${data.n}`, small: `wins · ${data.ties} ties · ${data.losses} losses`, color: 'text-wheat' },
              { big: String(data.summary.coordinator.invariant_violations_total ?? 0), small: 'constraint violations', color: 'text-leaf' },
            ].map((c, i) => (
              <motion.div key={c.small} className="rounded-xl bg-black/30 p-4" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.15 }}>
                <div className={`font-mono text-4xl font-extrabold ${c.color}`}>{c.big}</div>
                <div className="text-sm text-white/60">{c.small}</div>
              </motion.div>
            ))}
          </div>
          <div className="mt-6 h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={chart} barGap={4}>
                <XAxis dataKey="name" stroke="#7d8f83" fontSize={12} />
                <YAxis stroke="#7d8f83" fontSize={12} />
                <Tooltip contentStyle={{ background: '#16211a', border: '1px solid #2c3d32', borderRadius: 8 }} cursor={{ fill: '#ffffff08' }} />
                <Legend />
                <Bar dataKey="Coordinator" fill="#7bd88f" radius={[6, 6, 0, 0]} />
                <Bar dataKey="Baseline" fill="#5b6b61" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-2 text-xs text-white/40">Means per scenario. Higher is better for jobs; lower is better for travel and idle time.</p>
        </>
      )}
    </Backdrop>
  )
}
