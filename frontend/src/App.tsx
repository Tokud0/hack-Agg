import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useMemo, useState } from 'react'
import { api, useLiveState } from './api'
import { FieldMap, MapLegend, type Handoff } from './components/FieldMap'
import { FleetStrip } from './components/FleetStrip'
import { Gantt, GanttLegend } from './components/Gantt'
import { ChartIcon, ChatIcon, DownloadIcon, ListIcon, PauseIcon, PlayIcon, ResetIcon, SparkIcon, TractorIcon, BoltIcon, CloseIcon } from './components/Icons'
import { JobTable } from './components/JobTable'
import { BenchmarkModal, WhyDrawer } from './components/Overlays'
import { Counters, EventLog, ExplanationCard, InvariantPanel } from './components/Panels'
import { Copilot } from './components/tools/Copilot'
import { EventsTool } from './components/tools/EventsTool'
import { JobsTool } from './components/tools/JobsTool'
import type { LogEntry, MapInfo, Metrics, RunSnapshot, Strategy } from './types'
import { clock } from './theme'

const HANDOFF_MS = 3500
const FLASH_MS = 900
const SHIFT_HOURS = 12

type Tool = 'chat' | 'jobs' | 'events'

function useLatest(log: LogEntry[] | undefined, kind: string): LogEntry | undefined {
  return useMemo(() => [...(log ?? [])].reverse().find((e) => e.kind === kind), [log, kind])
}

interface MapPanelProps {
  run: RunSnapshot
  map: MapInfo
  title: string
  subtitle: string
  accent: string
  highlight: Set<string>
  handoffs: Handoff[]
  compareTo?: Metrics
  onSelectJob: (id: string) => void
}

function MapPanel({ run, map, title, subtitle, accent, highlight, handoffs, compareTo, onSelectJob }: MapPanelProps) {
  return (
    <section className="panel flex h-full min-h-0 flex-col p-3" style={{ boxShadow: `0 0 0 1px ${accent}22, 0 10px 40px -20px ${accent}66` }}>
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="text-sm font-extrabold uppercase tracking-widest" style={{ color: accent }}>{title}</h2>
        <span className="text-[11px] text-white/45">{subtitle}</span>
      </div>
      <Counters metrics={run.metrics} accent={accent} compareTo={compareTo} />
      <div className="mt-2 min-h-0 flex-1">
        <FieldMap run={run} map={map} highlight={highlight} handoffs={handoffs} onSelectJob={onSelectJob} />
      </div>
    </section>
  )
}

const GUIDE = [
  { n: 1, text: 'Press Run to start the shift' },
  { n: 2, text: 'Break a tractor and watch the re-plan' },
  { n: 3, text: 'Click any job to see why it went where it did' },
  { n: 4, text: 'Ask the copilot or forecast "what if"' },
]

function Guide({ onClose }: { onClose: () => void }) {
  return (
    <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, height: 0 }}
      className="flex flex-wrap items-center gap-x-6 gap-y-1 rounded-xl border border-leaf/20 bg-leaf/5 px-4 py-2 text-[12.5px]">
      <span className="font-bold text-leaf">How to use</span>
      {GUIDE.map((g) => (
        <span key={g.n} className="flex items-center gap-2 text-white/75">
          <span className="grid h-5 w-5 place-items-center rounded-full bg-leaf/20 text-[11px] font-bold text-leaf">{g.n}</span>{g.text}
        </span>
      ))}
      <button type="button" onClick={onClose} aria-label="Hide guide" className="ml-auto text-white/40 hover:text-white"><CloseIcon size={14} /></button>
    </motion.div>
  )
}

const TOOLS: { id: Tool; label: string; icon: typeof ChatIcon }[] = [
  { id: 'chat', label: 'Copilot chat', icon: ChatIcon },
  { id: 'jobs', label: 'Add jobs', icon: ListIcon },
  { id: 'events', label: 'Events & what-if', icon: BoltIcon },
]

export default function App() {
  const { view, connected } = useLiveState()
  const [map, setMap] = useState<MapInfo | null>(null)
  const [provider, setProvider] = useState('offline')
  const [hoverJobs, setHoverJobs] = useState<string[]>([])
  const [autoHighlight, setAutoHighlight] = useState<string[]>([])
  const [handoffs, setHandoffs] = useState<Handoff[]>([])
  const [whyJob, setWhyJob] = useState<string | null>(null)
  const [showBench, setShowBench] = useState(false)
  const [showGuide, setShowGuide] = useState(true)
  const [tool, setTool] = useState<Tool>('chat')
  const [ganttStrategy, setGanttStrategy] = useState<Strategy>('coordinator')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.map().then(setMap).catch(() => setError('Backend not reachable on :8000'))
    api.health().then((h) => setProvider(h.provider)).catch(() => setProvider('offline'))
  }, [connected, view?.scenario])

  const coord = view?.runs.coordinator
  const base = view?.runs.baseline
  const latest = useLatest(coord?.log, 'replan')
  const latestEvent = useLatest(coord?.log, 'event')

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
  const isBreakdownFlash = latestEvent?.data.type === 'breakdown'

  const act = async (fn: () => Promise<unknown>) => {
    try {
      setError(null)
      await fn()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed')
    }
  }
  const breakdown = (id: string) => act(() => api.event({ type: 'breakdown', tractor_id: id }))

  if (!view || !map || !coord || !base) {
    return (
      <div className="grid h-full place-items-center text-white/60">
        <div className="text-center">
          <TractorIcon size={40} className="blink mx-auto text-leaf" />
          <div className="mt-2">{error ?? 'Connecting to the coordinator…'}</div>
          <div className="mt-1 text-xs text-white/35">Start the backend: uvicorn api.main:app --port 8000</div>
        </div>
      </div>
    )
  }

  const explanation = latest ? view.explanations[String(latest.index)] : undefined
  const shiftShare = Math.min(1, coord.time / SHIFT_HOURS)
  const nodes = [map.depot.id, ...map.fields.map((f) => f.id)]

  return (
    <div className="flex min-h-full flex-col gap-3 p-3">
      <AnimatePresence>
        {isBreakdownFlash && (
          <motion.div key={latestEvent?.index} className="pointer-events-none fixed inset-0 z-40"
            style={{ boxShadow: 'inset 0 0 160px 40px #ff3b3b' }}
            initial={{ opacity: 0.9 }} animate={{ opacity: 0 }} transition={{ duration: FLASH_MS / 1000 }} />
        )}
      </AnimatePresence>

      <header className="panel flex flex-wrap items-center gap-5 px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-leaf/15 text-leaf"><TractorIcon size={22} /></span>
          <div>
            <div className="text-base font-extrabold tracking-tight">RUN THE FLEET</div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-white/45">Fleet coordinator · {view.scenario}</div>
          </div>
        </div>

        <div className="min-w-[150px]">
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-3xl font-bold text-leaf">{clock(coord.time)}</span>
            <span className="text-[10px] uppercase tracking-wider text-white/40">shift time</span>
          </div>
          <div className="mt-1 h-1 overflow-hidden rounded-full bg-white/10">
            <motion.div className="h-full bg-leaf" animate={{ width: `${shiftShare * 100}%` }} transition={{ duration: 0.15 }} />
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <button type="button" onClick={() => act(() => api.control(view.running ? 'pause' : 'play'))}
            className="flex items-center gap-1.5 rounded-lg bg-leaf px-4 py-1.5 text-sm font-extrabold text-black hover:brightness-110">
            {view.running ? <><PauseIcon size={14} />Pause</> : <><PlayIcon size={14} />Run</>}
          </button>
          <div className="flex rounded-lg bg-black/30 p-0.5" role="group" aria-label="Simulation speed">
            {map.speeds.map((s) => (
              <button type="button" key={s} onClick={() => act(() => api.control('speed', s))}
                className={`rounded-md px-2 py-1 font-mono text-xs ${view.speed === s ? 'bg-white/20 text-white' : 'text-white/45 hover:text-white'}`}>{s}x</button>
            ))}
          </div>
        </div>

        <div className="ml-auto flex items-center gap-2">
          <button type="button" onClick={() => setShowBench(true)} className="flex items-center gap-1.5 rounded-lg bg-wheat px-3 py-1.5 text-xs font-extrabold text-black hover:brightness-110"><ChartIcon size={14} />Benchmark x50</button>
          <a href="/api/export" download="event-log.json" className="flex items-center gap-1.5 rounded-lg bg-white/10 px-3 py-1.5 text-xs hover:bg-white/20"><DownloadIcon size={14} />Event log</a>
          <button type="button" onClick={() => act(() => api.control('reset'))} className="flex items-center gap-1.5 rounded-lg bg-white/10 px-3 py-1.5 text-xs hover:bg-white/20"><ResetIcon size={14} />Reset</button>
          <span className={`flex items-center gap-1 rounded-full px-2 py-1 text-[11px] ${provider !== 'offline' ? 'bg-wheat/15 text-wheat' : 'bg-white/5 text-white/40'}`}>
            <SparkIcon size={11} />{provider !== 'offline' ? `AI: ${provider}` : 'AI offline'}
          </span>
          <span className={`h-2.5 w-2.5 rounded-full ${connected ? 'bg-leaf' : 'bg-alarm'}`} title={connected ? 'live' : 'disconnected'} />
        </div>
      </header>

      <AnimatePresence>{showGuide && <Guide onClose={() => setShowGuide(false)} />}</AnimatePresence>
      {error && <div className="rounded-lg border border-alarm/40 bg-alarm/10 px-3 py-1.5 text-sm text-alarm">{error}</div>}

      <main className="grid flex-1 grid-cols-1 gap-3 xl:grid-cols-[1fr_1fr_400px]">
        <div className="h-[600px]">
          <MapPanel run={base} map={map} title="Baseline" subtitle="first come, first served · no re-planning" accent="#8fa396"
            highlight={new Set()} handoffs={[]} onSelectJob={setWhyJob} />
        </div>
        <div className="h-[600px]">
          <MapPanel run={coord} map={map} title="Our coordinator" subtitle="constraint-safe re-planning" accent="#7bd88f"
            highlight={highlight} handoffs={handoffs} compareTo={base.metrics} onSelectJob={setWhyJob} />
        </div>

        <aside className="flex min-h-0 flex-col gap-3 xl:row-span-5">
          <ExplanationCard explanation={explanation} pending={!!latest} onHover={setHoverJobs} />
          <InvariantPanel replan={latest?.data} entryIndex={latest?.index ?? 0} />
          <div className="panel flex min-h-[520px] flex-1 flex-col p-3">
            <div className="mb-3 grid grid-cols-3 gap-1 rounded-lg bg-black/30 p-1" role="tablist">
              {TOOLS.map(({ id, label, icon: Icon }) => (
                <button type="button" role="tab" aria-selected={tool === id} key={id} onClick={() => setTool(id)}
                  className={`flex items-center justify-center gap-1.5 rounded-md py-1.5 text-[11.5px] font-semibold ${tool === id ? 'bg-white/15 text-white' : 'text-white/45 hover:text-white'}`}>
                  <Icon size={13} />{label}
                </button>
              ))}
            </div>
            <div className="min-h-0 flex-1">
              {tool === 'chat' && <Copilot />}
              {tool === 'jobs' && <JobsTool fields={map.fields.map((f) => f.id)} nowHours={coord.time} />}
              {tool === 'events' && <EventsTool tractors={coord.tractors} jobs={coord.jobs} nodes={nodes} />}
            </div>
          </div>
        </aside>

        <div className="px-1 xl:col-span-2"><MapLegend /></div>

        <section className="xl:col-span-2">
          <div className="mb-2 flex items-baseline justify-between px-1">
            <h3 className="text-xs font-bold uppercase tracking-widest text-white/60">Fleet status</h3>
            <span className="text-[11px] text-white/35">our coordinator · live</span>
          </div>
          <FleetStrip tractors={coord.tractors} jobs={coord.jobs} onBreak={breakdown} onSelectJob={setWhyJob} />
        </section>

        <section className="panel p-3 xl:col-span-2">
          <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-xs font-bold uppercase tracking-widest text-white/60">Schedule · click a block to ask "why?"</h3>
            <div className="flex gap-1 rounded-md bg-black/30 p-0.5 text-[11px]">
              {(['coordinator', 'baseline'] as Strategy[]).map((s) => (
                <button type="button" key={s} onClick={() => setGanttStrategy(s)}
                  className={`rounded px-2 py-0.5 ${ganttStrategy === s ? 'bg-white/15' : 'text-white/45'}`}>{s === 'coordinator' ? 'our coordinator' : 'baseline'}</button>
              ))}
            </div>
          </div>
          <Gantt run={view.runs[ganttStrategy]} highlight={highlight} onSelectJob={setWhyJob} />
          <div className="mt-1"><GanttLegend /></div>
        </section>

        <section className="panel flex h-64 flex-col p-3">
          <h3 className="mb-1 text-xs font-bold uppercase tracking-widest text-white/60">Jobs</h3>
          <div className="min-h-0 flex-1"><JobTable jobs={coord.jobs} highlight={highlight} onSelectJob={setWhyJob} /></div>
        </section>
        <section className="panel flex h-64 flex-col p-3">
          <h3 className="mb-1 text-xs font-bold uppercase tracking-widest text-white/60">Event log</h3>
          <div className="min-h-0 flex-1"><EventLog log={coord.log} /></div>
        </section>
      </main>

      <AnimatePresence>
        {whyJob && <WhyDrawer key={whyJob} jobId={whyJob} onClose={() => setWhyJob(null)} />}
        {showBench && <BenchmarkModal onClose={() => setShowBench(false)} />}
      </AnimatePresence>
    </div>
  )
}
