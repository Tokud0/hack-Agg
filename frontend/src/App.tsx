import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useMemo, useState } from 'react'
import { api, useLiveState } from './api'
import type { Handoff } from './components/FieldMap'
import { TractorIcon } from './components/Icons'
import { BenchmarkModal, BriefingModal, WhyDrawer } from './components/Overlays'
import { ExplanationCard, InvariantPanel } from './components/Panels'
import { RadioFeed } from './components/radio/RadioFeed'
import { NavRail } from './components/shell/NavRail'
import { SideDock, type DockTab } from './components/shell/SideDock'
import { TopBar } from './components/shell/TopBar'
import { Copilot } from './components/tools/Copilot'
import { EventsTool } from './components/tools/EventsTool'
import { JobsTool } from './components/tools/JobsTool'
import { useHashView } from './nav'
import { useAgentRadio, type RadioMode } from './radio'
import type { BaselineKind } from './strategies'
import type { LogEntry, MapInfo } from './types'
import { CompareView } from './views/CompareView'
import { LiveView } from './views/LiveView'
import { LogView } from './views/LogView'
import { OrchestrationView } from './views/OrchestrationView'
import { ScenarioView } from './views/ScenarioView'
import { ScheduleView } from './views/ScheduleView'

const HANDOFF_MS = 3500
const FLASH_MS = 900

const NAV_OPEN_KEY = 'fleet.navOpen'

/** The menu stays the way the operator left it; storage may be unavailable (private window). */
function readNavOpen(): boolean {
  try {
    return window.localStorage.getItem(NAV_OPEN_KEY) !== 'false'
  } catch {
    return true
  }
}

function useLatest(log: LogEntry[] | undefined, kind: string): LogEntry | undefined {
  return useMemo(() => [...(log ?? [])].reverse().find((e) => e.kind === kind), [log, kind])
}

export default function App() {
  const { view: session, connected } = useLiveState()
  const [page, navigate] = useHashView()
  const [map, setMap] = useState<MapInfo | null>(null)
  const [provider, setProvider] = useState('offline')
  const [hoverJobs, setHoverJobs] = useState<string[]>([])
  const [autoHighlight, setAutoHighlight] = useState<string[]>([])
  const [handoffs, setHandoffs] = useState<Handoff[]>([])
  const [whyJob, setWhyJob] = useState<string | null>(null)
  const [showBench, setShowBench] = useState(false)
  const [showBriefing, setShowBriefing] = useState(false)
  const [dockTab, setDockTab] = useState<DockTab>('radio')
  const [seenReplan, setSeenReplan] = useState<number | undefined>(undefined)
  const [baselineKind, setBaselineKind] = useState<BaselineKind>('baseline')
  const [error, setError] = useState<string | null>(null)
  const [isNavOpen, setIsNavOpen] = useState(readNavOpen)
  const [radioMode, setRadioMode] = useState<RadioMode>('summary')

  useEffect(() => {
    api.map().then(setMap).catch(() => setError('Backend not reachable on :8000'))
    api.health().then((h) => setProvider(h.provider)).catch(() => setProvider('offline'))
  }, [connected, session?.session_id])

  const coord = session?.runs.coordinator
  const base = session?.runs[baselineKind]
  const latest = useLatest(coord?.log, 'replan')
  const latestEvent = useLatest(coord?.log, 'event')
  const radio = useAgentRadio(coord?.log, session?.explanations, coord?.time ?? 0, session?.session_id, radioMode === 'summary')
  const isInitialPlan = latest?.data.diff?.trigger.type === 'initial_plan'

  // React to each new re-plan: handoff arrows on the map, temporary highlight, and surface the explanation.
  useEffect(() => {
    if (!latest?.data.diff) return
    const changes = latest.data.diff.changes
    const moves = changes.filter((c) => c.before.startsWith('T') && c.after.startsWith('T') && c.before !== c.after)
    setHandoffs(moves.map((c) => ({ key: `${latest.index}-${c.job_id}`, from: c.before, to: c.after, jobId: c.job_id })))
    setAutoHighlight(isInitialPlan ? [] : changes.map((c) => c.job_id))
    // Bring the agents' conversation into view. The chat is where the operator confirms events, so it is never yanked away.
    if (!isInitialPlan) setDockTab((tab) => (tab === 'chat' ? tab : 'radio'))
    const t = window.setTimeout(() => { setHandoffs([]); setAutoHighlight([]) }, HANDOFF_MS)
    return () => window.clearTimeout(t)
  }, [latest?.index]) // eslint-disable-line react-hooks/exhaustive-deps -- fire once per re-plan

  useEffect(() => {
    if (dockTab === 'replan') setSeenReplan(latest?.index)
  }, [dockTab, latest?.index])

  // What each tractor's agent said last in the latest planning round, shown on its card.
  const lastWords = useMemo(
    () => Object.fromEntries((latest?.data.messages ?? []).filter((m) => m.sender.startsWith('T')).map((m) => [m.sender, m.text])),
    [latest],
  )
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
  const toggleNav = () => {
    const next = !isNavOpen
    setIsNavOpen(next)
    try {
      window.localStorage.setItem(NAV_OPEN_KEY, String(next))
    } catch {
      // Not being able to remember the choice is harmless.
    }
  }
  const breakdown = (id: string) => act(() => api.event({ type: 'breakdown', tractor_id: id }))

  if (!session || !map || !coord || !base) {
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

  const explanation = latest ? session.explanations[String(latest.index)] : undefined
  const nodes = [map.depot.id, ...map.fields.map((f) => f.id)]
  const hasUnreadReplan = dockTab !== 'replan' && !isInitialPlan && latest !== undefined && latest.index !== seenReplan

  const replanPanel = (
    <div className="flex h-full flex-col gap-3 overflow-y-auto">
      <ExplanationCard explanation={explanation} pending={!!latest} onHover={setHoverJobs} />
      <InvariantPanel replan={latest?.data} entryIndex={latest?.index ?? 0} />
      {isInitialPlan && (
        <p className="rounded-xl border border-dashed border-white/10 px-3 py-2.5 text-[12.5px] leading-relaxed text-white/50">
          This is the opening plan. Break a tractor from its card on the Live page, or use the Events tab, and the new plan with its explanation appears here.
        </p>
      )}
    </div>
  )

  return (
    <div className="flex min-h-full flex-col xl:h-full">
      <AnimatePresence>
        {isBreakdownFlash && (
          <motion.div key={latestEvent?.index} className="pointer-events-none fixed inset-0 z-40"
            style={{ boxShadow: 'inset 0 0 160px 40px #ff3b3b' }}
            initial={{ opacity: 0.9 }} animate={{ opacity: 0 }} transition={{ duration: FLASH_MS / 1000 }} />
        )}
      </AnimatePresence>

      <TopBar scenario={session.scenario} time={coord.time} isRunning={session.running} speed={session.speed} speeds={map.speeds}
        provider={provider} isConnected={connected}
        onTogglePlay={() => act(() => api.control(session.running ? 'pause' : 'play'))}
        onSpeed={(s) => act(() => api.control('speed', s))}
        onReset={() => act(() => api.control('reset'))}
        onRandom={(trouble, seed) => act(async () => api.uploadScenario(await api.randomScenario(trouble, seed)))}
        surprisesLeft={session.surprises_left ?? 0}
        isNavOpen={isNavOpen} onToggleNav={toggleNav} onBriefing={() => setShowBriefing(true)} weatherHolds={session.weather_holds ?? []} />

      <div className="flex flex-1 flex-col xl:min-h-0 xl:flex-row">
        {isNavOpen && <NavRail view={page} onNavigate={navigate} />}

        <main className="flex min-w-0 flex-1 flex-col gap-3 p-3 xl:overflow-y-auto">
          {error && <div role="alert" className="rounded-lg border border-alarm/40 bg-alarm/10 px-3 py-1.5 text-sm text-alarm">{error}</div>}
          <div className="min-h-0 flex-1">
            {page === 'live' && (
              <LiveView run={coord} map={map} baselineKind={baselineKind} baselineMetrics={base.metrics}
                highlight={highlight} handoffs={handoffs} lastWords={lastWords} speech={radio.speech} onBreak={breakdown} onSelectJob={setWhyJob} />
            )}
            {page === 'orchestration' && <OrchestrationView log={coord.log} explanations={session.explanations} />}
            {page === 'schedule' && <ScheduleView runs={session.runs} highlight={highlight} onSelectJob={setWhyJob} />}
            {page === 'compare' && (
              <CompareView coordinator={coord} baseline={base} baselineKind={baselineKind} onBaselineKind={setBaselineKind} map={map}
                highlight={highlight} handoffs={handoffs} onSelectJob={setWhyJob} onOpenBenchmark={() => setShowBench(true)} speech={radio.speech} />
            )}
            {page === 'log' && <LogView log={coord.log} />}
            {page === 'scenario' && <ScenarioView onStarted={() => navigate('live')} />}
          </div>
        </main>

        <SideDock tab={dockTab} onTab={setDockTab} hasUnreadReplan={hasUnreadReplan}
          panels={{
            radio: <RadioFeed items={radio.items} backlog={radio.backlog} mode={radioMode} onMode={setRadioMode} />,
            replan: replanPanel,
            chat: <Copilot />,
            jobs: <JobsTool fields={map.fields.map((f) => f.id)} nowHours={coord.time} />,
            events: <EventsTool tractors={coord.tractors} jobs={coord.jobs} nodes={nodes} scheduledFaults={session.scheduled_faults ?? []} />,
          }} />
      </div>

      <AnimatePresence>
        {whyJob && <WhyDrawer key={whyJob} jobId={whyJob} onClose={() => setWhyJob(null)} />}
        {showBench && <BenchmarkModal onClose={() => setShowBench(false)} />}
        {showBriefing && <BriefingModal onClose={() => setShowBriefing(false)} />}
      </AnimatePresence>
    </div>
  )
}
