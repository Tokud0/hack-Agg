import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useMemo, useState } from 'react'
import { api, useLiveState } from './api'
import { Copilot } from './components/Copilot'
import { FieldMap, type Handoff } from './components/FieldMap'
import { Gantt } from './components/Gantt'
import { JobTable } from './components/JobTable'
import { BenchmarkModal, WhyDrawer } from './components/Overlays'
import { Counters, EventLog, ExplanationCard, InvariantPanel } from './components/Panels'
import type { LogEntry, MapInfo, ProposedEvent, RunSnapshot, Strategy } from './types'
import { clock } from './theme'

const HANDOFF_MS = 3500
const FLASH_MS = 900

function useLatestReplan(log: LogEntry[] | undefined): LogEntry | undefined {
  return useMemo(() => [...(log ?? [])].reverse().find((e) => e.kind === 'replan'), [log])
}

function MapPanel({ run, map, title, subtitle, accent, highlight, handoffs, onSelectJob }: {
  run: RunSnapshot; map: MapInfo; title: string; subtitle: string; accent: string
  highlight: Set<string>; handoffs: Handoff[]; onSelectJob: (id: string) => void
}) {
  return (
    <section className="panel flex min-h-0 flex-col p-3" style={{ boxShadow: `0 0 0 1px ${accent}22, 0 10px 40px -20px ${accent}66` }}>
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="text-sm font-extrabold uppercase tracking-widest" style={{ color: accent }}>{title}</h2>
        <span className="text-[11px] text-white/45">{subtitle}</span>
      </div>
      <Counters metrics={run.metrics} accent={accent} />
      <div className="mt-2 min-h-0 flex-1">
        <FieldMap run={run} map={map} highlight={highlight} handoffs={handoffs} onSelectJob={onSelectJob} />
      </div>
    </section>
  )
}

export default function App() {
  const { view, connected } = useLiveState()
  const [map, setMap] = useState<MapInfo | null>(null)
  const [llm, setLlm] = useState(false)
  const [hoverJobs, setHoverJobs] = useState<string[]>([])
  const [autoHighlight, setAutoHighlight] = useState<string[]>([])
  const [handoffs, setHandoffs] = useState<Handoff[]>([])
  const [whyJob, setWhyJob] = useState<string | null>(null)
  const [showBench, setShowBench] = useState(false)
  const [flash, setFlash] = useState(0)
  const [ganttStrategy, setGanttStrategy] = useState<Strategy>('coordinator')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.map().then(setMap).catch(() => setError('Backend not reachable on :8000'))
    api.health().then((h) => setLlm(h.llm)).catch(() => setLlm(false))
  }, [connected])

  const coord = view?.runs.coordinator
  const base = view?.runs.baseline
  const latest = useLatestReplan(coord?.log)

  // React to each new re-plan: handoff arrows on the map + temporary highlight.
  useEffect(() => {
    if (!latest?.data.diff) return
    const changes = latest.data.diff.changes
    const moves = changes.filter((c) => c.before.startsWith('T') && c.after.startsWith('T') && c.before !== c.after)
    setHandoffs(moves.map((c) => ({ key: `${latest.index}-${c.job_id}`, from: c.before, to: c.after, jobId: c.job_id })))
    setAutoHighlight(latest.data.diff.trigger.type === 'initial_plan' ? [] : changes.map((c) => c.job_id))
    const t = window.setTimeout(() => { setHandoffs([]); setAutoHighlight([]) }, HANDOFF_MS)
    return () => window.clearTimeout(t)
  }, [latest?.index]) // eslint-disable-line react-hooks/exhaustive-deps -- fire once per re-plan

  const highlight = useMemo(() => new Set([...hoverJobs, ...autoHighlight]), [hoverJobs, autoHighlight])

  const run = async (fn: () => Promise<unknown>) => {
    try {
      setError(null)
      await fn()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed')
    }
  }
  const breakdown = (id: string) => run(async () => {
    setFlash((f) => f + 1)
    await api.event({ type: 'breakdown', tractor_id: id } satisfies ProposedEvent)
  })

  if (!view || !map || !coord || !base) {
    return (
      <div className="grid h-full place-items-center text-white/60">
        <div className="text-center">
          <div className="blink text-3xl">🚜</div>
          <div className="mt-2">{error ?? 'Connecting to the coordinator…'}</div>
          <div className="mt-1 text-xs text-white/35">Start the backend: uvicorn api.main:app --port 8000</div>
        </div>
      </div>
    )
  }

  const explanation = latest ? view.explanations[String(latest.index)] : undefined

  return (
    <div className="flex min-h-full flex-col gap-3 p-3">
      <AnimatePresence>
        {flash > 0 && (
          <motion.div key={flash} className="pointer-events-none fixed inset-0 z-40"
            style={{ boxShadow: 'inset 0 0 160px 40px #ff3b3b' }}
            initial={{ opacity: 0.9 }} animate={{ opacity: 0 }} transition={{ duration: FLASH_MS / 1000 }} />
        )}
      </AnimatePresence>

      <header className="panel flex flex-wrap items-center gap-4 px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="text-2xl">🚜</span>
          <div>
            <div className="text-base font-extrabold tracking-tight">RUN THE FLEET</div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-white/45">Fleet coordinator · {view.scenario}</div>
          </div>
        </div>
        <div className="font-mono text-3xl font-bold text-leaf">{clock(coord.time)}</div>
        <div className="flex items-center gap-1">
          <button type="button" onClick={() => run(() => api.control(view.running ? 'pause' : 'play'))}
            className="rounded-lg bg-leaf px-4 py-1.5 text-sm font-extrabold text-black hover:brightness-110">
            {view.running ? '❚❚ Pause' : '▶ Run'}
          </button>
          {map.speeds.map((s) => (
            <button type="button" key={s} onClick={() => run(() => api.control('speed', s))}
              className={`rounded-md px-2 py-1 font-mono text-xs ${view.speed === s ? 'bg-white/20 text-white' : 'text-white/45 hover:bg-white/10'}`}>{s}x</button>
          ))}
        </div>
        <div className="flex items-center gap-1.5">
          {coord.tractors.map((t) => (
            <button type="button" key={t.id} disabled={t.status === 'broken'} onClick={() => breakdown(t.id)}
              className="rounded-lg border border-alarm/40 bg-alarm/10 px-2.5 py-1.5 text-xs font-bold text-alarm hover:bg-alarm/25 disabled:opacity-30">
              💥 Break {t.id}
            </button>
          ))}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <button type="button" onClick={() => setShowBench(true)} className="rounded-lg bg-wheat px-3 py-1.5 text-xs font-extrabold text-black hover:brightness-110">📊 Benchmark ×50</button>
          <a href="/api/export" download="event-log.json" className="rounded-lg bg-white/10 px-3 py-1.5 text-xs hover:bg-white/20">⬇ Event log</a>
          <button type="button" onClick={() => run(() => api.control('reset'))} className="rounded-lg bg-white/10 px-3 py-1.5 text-xs hover:bg-white/20">↺ Reset</button>
          <span className={`flex items-center gap-1 text-[11px] ${llm ? 'text-wheat' : 'text-white/40'}`}>✦ {llm ? 'Claude on' : 'offline'}</span>
          <span className={`h-2.5 w-2.5 rounded-full ${connected ? 'bg-leaf' : 'bg-alarm'}`} title={connected ? 'live' : 'disconnected'} />
        </div>
      </header>
      {error && <div className="rounded-lg border border-alarm/40 bg-alarm/10 px-3 py-1.5 text-sm text-alarm">{error}</div>}

      <main className="grid flex-1 grid-cols-1 gap-3 xl:grid-cols-[1fr_1fr_380px]">
        <div className="h-[460px] xl:h-auto xl:min-h-[440px]">
          <MapPanel run={base} map={map} title="Baseline" subtitle="first come, first served" accent="#8fa396"
            highlight={new Set()} handoffs={[]} onSelectJob={setWhyJob} />
        </div>
        <div className="h-[460px] xl:h-auto xl:min-h-[440px]">
          <MapPanel run={coord} map={map} title="Coordinator" subtitle="constraint-safe re-planning" accent="#7bd88f"
            highlight={highlight} handoffs={handoffs} onSelectJob={setWhyJob} />
        </div>

        <aside className="flex min-h-0 flex-col gap-3 xl:row-span-3">
          <ExplanationCard explanation={explanation} pending={!!latest} onHover={setHoverJobs} />
          <InvariantPanel replan={latest?.data} entryIndex={latest?.index ?? 0} />
          <div className="min-h-[320px] flex-1"><Copilot /></div>
        </aside>

        <section className="panel p-3 xl:col-span-2">
          <div className="mb-1 flex items-center justify-between">
            <h3 className="text-xs font-bold uppercase tracking-widest text-white/60">Schedule · click a block to ask "why?"</h3>
            <div className="flex gap-1 text-[11px]">
              {(['coordinator', 'baseline'] as Strategy[]).map((s) => (
                <button type="button" key={s} onClick={() => setGanttStrategy(s)}
                  className={`rounded px-2 py-0.5 ${ganttStrategy === s ? 'bg-white/15' : 'text-white/45'}`}>{s}</button>
              ))}
            </div>
          </div>
          <Gantt run={view.runs[ganttStrategy]} highlight={highlight} onSelectJob={setWhyJob} />
        </section>

        <section className="panel h-56 p-3"><JobTable jobs={coord.jobs} highlight={highlight} onSelectJob={setWhyJob} /></section>
        <section className="panel h-56 p-3"><EventLog log={coord.log} /></section>
      </main>

      <AnimatePresence>
        {whyJob && <WhyDrawer key={whyJob} jobId={whyJob} onClose={() => setWhyJob(null)} />}
        {showBench && <BenchmarkModal onClose={() => setShowBench(false)} />}
      </AnimatePresence>
    </div>
  )
}
