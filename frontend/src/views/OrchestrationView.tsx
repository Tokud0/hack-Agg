import { useState } from 'react'
import { api } from '../api'
import { ShieldIcon } from '../components/Icons'
import { Conversation } from '../components/orchestration/Conversation'
import { IncidentAgent } from '../components/orchestration/IncidentAgent'
import { CandidateTable, FaultTestCard, Outcome } from '../components/orchestration/Details'
import { Pipeline } from '../components/orchestration/Pipeline'
import { describeTrigger } from '../labels'
import { ViewHeader } from '../components/shell/ViewHeader'
import { clock } from '../theme'
import type { Explanation, FaultTestResult, IncidentRecord, LogEntry } from '../types'

const PRINCIPLES = [
  { title: 'One agent per tractor', text: 'Each answers only for itself: its place, fuel, implement and queue. A claimed job is never planned twice.' },
  { title: 'Nothing reaches a tractor unchecked', text: 'Every plan passes four safety checks. One failure and the last valid plan stays.' },
  { title: 'The LLM talks, the code decides', text: 'Bids are computed, not guessed. The LLM only reads events in and explains results out.' },
]

interface OrchestrationViewProps {
  log: LogEntry[]
  explanations: Record<string, Explanation>
  incidentReviews: Record<string, IncidentRecord>
}

export function OrchestrationView({ log, explanations, incidentReviews }: OrchestrationViewProps) {
  // null = follow the newest re-plan as it happens.
  const [pinnedIndex, setPinnedIndex] = useState<number | null>(null)
  const [faultTest, setFaultTest] = useState<FaultTestResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const replans = log.filter((e) => e.kind === 'replan' && e.data.trace)
  const latest = replans.at(-1)
  const selected = replans.find((e) => e.index === pinnedIndex) ?? latest

  const runFaultTest = async () => {
    try {
      setError(null)
      setFaultTest(await api.faultTest())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Safety gate test failed')
    }
  }

  const trace = selected?.data.trace
  const explanation = selected ? explanations[String(selected.index)] : undefined

  return (
    <div className="flex flex-col gap-3">
      <ViewHeader title="Agents" description="Every tractor has its own agent. The Agronomy Agent sets what the weather allows, the Navigation Agent routes, the Fleet Agent runs the auction, the Safety Agent has the last word."
        actions={<button type="button" onClick={runFaultTest}
          className="flex items-center gap-1.5 rounded-lg border border-sky-300/40 px-3 py-1.5 text-xs font-bold text-sky-300 hover:bg-sky-400/10"><ShieldIcon size={14} />Test the Safety Agent</button>} />

      <ul className="grid gap-2 md:grid-cols-3">
        {PRINCIPLES.map((p) => (
          <li key={p.title} className="rounded-xl border border-white/8 bg-black/20 px-3 py-2">
            <div className="text-[12.5px] font-bold text-white">{p.title}</div>
            <div className="mt-0.5 text-[11.5px] leading-snug text-white/50">{p.text}</div>
          </li>
        ))}
      </ul>

      {error && <div role="alert" className="rounded-lg border border-alarm/40 bg-alarm/10 px-3 py-1.5 text-sm text-alarm">{error}</div>}
      {faultTest && <FaultTestCard result={faultTest} onClose={() => setFaultTest(null)} />}

      <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Re-plans of this shift">
        <span className="mr-1 text-[10px] font-bold uppercase tracking-widest text-white/45">Re-plans this shift</span>
        {replans.map((e) => {
          const isSelected = e.index === selected?.index
          return (
            <button type="button" key={e.index} aria-pressed={isSelected} onClick={() => setPinnedIndex(e.index === latest?.index ? null : e.index)}
              className={`rounded-lg border px-2.5 py-1 text-[11.5px] ${isSelected ? 'border-leaf/50 bg-leaf/12 text-leaf' : 'border-white/10 text-white/60 hover:bg-white/5 hover:text-white'}`}>
              <span className="mr-1.5 font-mono text-white/45">{clock(e.time)}</span>{describeTrigger(e.data.diff?.trigger ?? {})}
            </button>
          )
        })}
      </div>

      {selected && trace ? (
        <>
          <Pipeline entry={selected} trace={trace} explanation={explanation} />
          <div className="grid items-start gap-3 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
            <Conversation replanIndex={selected.index} messages={selected.data.messages ?? []} />
            <Outcome replan={selected.data} explanation={explanation} />
          </div>
          <IncidentAgent record={incidentReviews[String(selected.index)]} isIncident={selected.data.diff?.trigger.type !== 'initial_plan'} replanIndex={selected.index} />
          <CandidateTable candidates={trace.plan.candidates} />
        </>
      ) : (
        <p className="panel p-6 text-center text-sm text-white/45">No plan yet. Restart the shift to see the first one.</p>
      )}
    </div>
  )
}
