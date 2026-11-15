import { useState } from 'react'
import { api } from '../../api'
import { SparkIcon } from '../Icons'
import type { IncidentRecord, ToolCall } from '../../types'
import { SourceBadge } from '../Panels'

const SEVERITY: Record<string, string> = {
  low: 'bg-leaf/15 text-leaf',
  medium: 'bg-wheat/20 text-wheat',
  high: 'bg-alarm/20 text-alarm',
}
const FINISH_TOOL = 'file_incident_review'
const heading = 'text-xs font-bold uppercase tracking-widest text-white/60'

const signature = (call: ToolCall): string => {
  const args = Object.entries(call.arguments).map(([key, value]) => `${key}: ${JSON.stringify(value)}`).join(', ')
  return call.tool === FINISH_TOOL ? `${call.tool}(…)` : `${call.tool}(${args})`
}

function CallRow({ call, step }: { call: ToolCall; step: number }) {
  const [isOpen, setIsOpen] = useState(false)
  return (
    <li className="border-t border-white/5 py-1.5">
      <button type="button" onClick={() => setIsOpen((open) => !open)} aria-expanded={isOpen} className="flex w-full items-center gap-2 text-left">
        <span className="grid h-5 w-5 shrink-0 place-items-center rounded-full bg-white/10 font-mono text-[10px] font-bold">{step}</span>
        <code className={`min-w-0 flex-1 truncate font-mono text-[12px] ${call.ok ? 'text-white/90' : 'text-alarm'}`}>{signature(call)}</code>
        <span className={`rounded px-1 text-[9.5px] font-bold uppercase ${call.chosen_by === 'model' ? 'bg-wheat/15 text-wheat' : 'bg-white/10 text-white/50'}`}>
          {call.chosen_by === 'model' ? 'chosen by the LLM' : 'fixed fallback'}
        </span>
        <span className="w-14 shrink-0 text-right font-mono text-[10.5px] text-white/40">{call.duration_ms.toFixed(1)} ms</span>
      </button>
      {isOpen && (
        <pre className="mt-1.5 max-h-56 overflow-auto rounded-lg bg-black/40 p-2 font-mono text-[10.5px] leading-snug text-white/70">
          {JSON.stringify(call.tool === FINISH_TOOL ? call.arguments : call.result, null, 2)}
        </pre>
      )}
      {!call.ok && !isOpen && <p className="mt-0.5 pl-7 text-[11px] text-alarm/80">Refused: {String(call.result.error ?? 'failed')}</p>}
    </li>
  )
}

interface IncidentAgentProps {
  record?: IncidentRecord
  /** The opening plan is not an incident, so the agent does not run for it. */
  isIncident: boolean
  replanIndex: number
}

/** The one LLM agent that acts: after the fleet has recovered, it investigates with tool calls and files a review. */
export function IncidentAgent({ record, isIncident, replanIndex }: IncidentAgentProps) {
  const [isBusy, setIsBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const isByModel = record !== undefined && record.source !== 'template'

  const investigate = async () => {
    setIsBusy(true)
    setError(null)
    try {
      await api.investigateIncident(replanIndex)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The agent could not investigate')
    } finally {
      setIsBusy(false)
    }
  }

  return (
    <section className="panel p-3" aria-label="Incident Response Agent">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className={heading}>Incident Response Agent · real tool calls</h2>
        <div className="flex items-center gap-2">
          {record && <SourceBadge source={record.source} />}
          {isIncident && (
            <button type="button" onClick={investigate} disabled={isBusy}
              className="flex items-center gap-1.5 rounded-lg bg-wheat px-3 py-1.5 text-xs font-extrabold text-black hover:brightness-110 disabled:opacity-50">
              <SparkIcon size={13} />{isBusy ? 'Agent is calling tools…' : isByModel ? 'Investigate again' : 'Let the LLM agent investigate'}
            </button>
          )}
        </div>
      </div>
      {error && <p role="alert" className="mt-1 text-[12px] text-alarm">{error}</p>}
      <p className="mt-1 text-[11.5px] leading-snug text-white/50">
        After the fleet has recovered by itself, an LLM agent can investigate the incident: it decides which tools to call, the server validates and runs them, and it files a review for the manager.
        Its tools only read; it cannot change the plan.
      </p>
      {!isIncident && <p className="mt-2 text-[12.5px] text-white/45">This is the opening plan, not an incident. Pick a re-plan caused by an event to see the agent at work.</p>}
      {isIncident && !record && <p className="mt-2 flex items-center gap-2 text-[12.5px] text-white/55"><span className="blink text-wheat">●</span>The agent is investigating…</p>}
      {record && (
        <>
          {record.review && (
            <div className="mt-2 rounded-lg bg-black/25 p-2.5">
              <div className="flex items-center gap-2">
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${SEVERITY[record.review.severity]}`}>{record.review.severity} severity</span>
                <span className="text-[10px] font-bold uppercase tracking-widest text-white/45">Review for the manager</span>
              </div>
              <p className="mt-1.5 text-[13px] leading-snug text-white/90">{record.review.finding}</p>
              <p className="mt-1 text-[12.5px] leading-snug text-white/65"><b className="text-white/85">Recommendation:</b> {record.review.recommendation}</p>
            </div>
          )}
          {record.source === 'template' && (
            <p className="mt-2 text-[11.5px] leading-snug text-wheat/90">
              This is the automatic check: the tools were run in a fixed order and the review was written by rule, with no LLM{record.notes.length ? ` (${record.notes.join('; ')})` : ''}.
              Press the button above and the LLM agent chooses its own tool calls.
            </p>
          )}
          <h3 className={`${heading} mt-3`}>Tool calls, in order · click one to see what it returned</h3>
          <ol>{record.calls.map((call, i) => <CallRow key={`${call.tool}-${i}`} call={call} step={i + 1} />)}</ol>
        </>
      )}
    </section>
  )
}
