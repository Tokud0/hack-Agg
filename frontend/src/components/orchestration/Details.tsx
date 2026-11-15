import { motion } from 'framer-motion'
import type { Explanation, FaultTestResult, JobChange, PlanCandidate, ReplanData } from '../../types'
import { tractorColor } from '../../theme'
import { AlertIcon, ArrowRightIcon, ShieldIcon } from '../Icons'
import { INVARIANT_LABELS } from '../../labels'
import { SourceBadge } from '../Panels'

const MIN_BAR_SHARE = 0.12
const heading = 'text-xs font-bold uppercase tracking-widest text-white/60'

const formatScore = (score: number | null): string => (score === null ? 'infeasible' : Math.round(score).toLocaleString('en-US'))

/** Bar length shows where a candidate sits between the worst and the best final score. */
function barShare(candidate: PlanCandidate, scores: number[]): number {
  if (candidate.score === null) return 0
  const min = Math.min(...scores)
  const max = Math.max(...scores)
  if (max === min) return 1
  return MIN_BAR_SHARE + (1 - MIN_BAR_SHARE) * ((candidate.score - min) / (max - min))
}

export function CandidateTable({ candidates }: { candidates: PlanCandidate[] }) {
  const scores = candidates.flatMap((c) => (c.score === null ? [] : [c.score]))
  return (
    <section className="panel p-3" aria-label="Planner candidates">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3">
        <h2 className={heading}>Fleet Agent: every auction round it tried</h2>
        <span className="text-[11px] text-white/40">score = priority-weighted work done, minus driving and late finishes</span>
      </div>
      <table className="mt-2 w-full text-[12px]">
        <thead className="text-left text-[10px] uppercase tracking-wider text-white/40">
          <tr><th className="py-1 font-semibold">Order jobs were called in</th><th className="font-semibold">Jobs placed</th><th className="font-semibold">First draft</th><th className="font-semibold">After improvement</th><th className="w-[30%]" /></tr>
        </thead>
        <tbody>
          {candidates.map((c) => (
            <tr key={c.name} className={`border-t border-white/5 ${c.is_winner ? 'text-leaf' : 'text-white/75'}`}>
              <td className="py-1.5 font-semibold">{c.name}{c.is_winner && <span className="ml-2 rounded bg-leaf/15 px-1.5 py-0.5 text-[10px] font-bold">chosen</span>}</td>
              <td className="font-mono">{c.jobs_assigned}</td>
              <td className="font-mono text-white/45">{formatScore(c.start_score)}</td>
              <td className="font-mono">{formatScore(c.score)}</td>
              <td>
                <div className="h-1.5 rounded-full bg-white/8">
                  <motion.div className={`h-full rounded-full ${c.is_winner ? 'bg-leaf' : 'bg-white/30'}`}
                    initial={{ width: 0 }} animate={{ width: `${barShare(c, scores) * 100}%` }} transition={{ duration: 0.5 }} />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

function Owner({ id }: { id: string }) {
  if (id.startsWith('T')) return <b style={{ color: tractorColor(id) }}>{id}</b>
  return <span className={id === 'unassignable' ? 'text-alarm' : 'text-white/45'}>{id === 'unassignable' ? 'not doable' : 'not planned'}</span>
}

export function ChangeRow({ change }: { change: JobChange }) {
  return (
    <li className="border-t border-white/5 py-1.5 text-[12.5px]">
      <div className="flex items-center gap-2">
        <span className="w-9 font-mono font-bold">{change.job_id}</span>
        <Owner id={change.before} /><ArrowRightIcon size={12} className="text-white/35" /><Owner id={change.after} />
        <span className="ml-auto text-[11px] text-white/40">{change.field_id} · P{change.priority}</span>
      </div>
      {change.reason && <div className="mt-0.5 pl-11 text-[11px] leading-snug text-alarm/75">{change.reason}</div>}
    </li>
  )
}

interface OutcomeProps {
  replan: Partial<ReplanData>
  explanation?: Explanation
}

/** Right-hand column: what the gate checked, what the dispatcher changed, what the explainer wrote. */
export function Outcome({ replan, explanation }: OutcomeProps) {
  const checked = replan.invariants?.checked ?? []
  const violations = replan.invariants?.violations ?? []
  const warnings = replan.invariants?.warnings ?? []
  const changes = replan.diff?.changes ?? []
  return (
    <section className="panel flex flex-col gap-3 p-3" aria-label="Result of this re-plan">
      <div>
        <h2 className={`${heading} flex items-center gap-1.5`}><ShieldIcon size={13} className="text-sky-300" />Safety Agent</h2>
        <ul className="mt-1.5 space-y-1 text-[12.5px]">
          {checked.map((name) => {
            const hasFailed = violations.some((v) => v.startsWith(name))
            return (
              <li key={name} className="flex items-center gap-2">
                <span className={`h-2 w-2 rounded-full ${hasFailed ? 'bg-alarm' : 'bg-leaf'}`} />
                <span className={hasFailed ? 'text-alarm' : 'text-white/80'}>{INVARIANT_LABELS[name] ?? name}</span>
              </li>
            )
          })}
        </ul>
        {warnings.map((w) => <p key={w} className="mt-1.5 text-[11.5px] leading-snug text-wheat">Warning, not caused by this plan: {w}.</p>)}
      </div>
      <div>
        <h2 className={heading}>Fleet Agent: who got what</h2>
        {changes.length === 0
          ? <p className="mt-1.5 text-[12.5px] text-white/45">No job changed hands.</p>
          : <ul className="mt-1">{changes.map((c) => <ChangeRow key={c.job_id} change={c} />)}</ul>}
      </div>
      <div>
        <div className="flex items-center justify-between">
          <h2 className={heading}>Explainer</h2>
          {explanation && <SourceBadge source={explanation.source} />}
        </div>
        <p className="mt-1.5 text-[12.5px] leading-relaxed text-white/75">{explanation?.summary ?? 'Writing the explanation…'}</p>
      </div>
    </section>
  )
}

export function FaultTestCard({ result, onClose }: { result: FaultTestResult; onClose: () => void }) {
  return (
    <motion.section initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} aria-label="Safety gate test result"
      className="rounded-xl border border-alarm/40 bg-alarm/8 p-3 text-[12.5px]">
      <div className="flex items-start gap-3">
        <AlertIcon size={18} className="mt-0.5 shrink-0 text-alarm" />
        <div className="min-w-0 flex-1">
          <div className="font-bold text-white">
            Test: we handed the Safety Agent a broken plan. {result.accepted ? 'It was NOT caught.' : 'It was vetoed, and the live plan was not touched.'}
          </div>
          <div className="mt-1 text-white/70">Injected fault: {result.fault}.</div>
          <ul className="mt-1.5 space-y-0.5 font-mono text-[11.5px] text-alarm">
            {result.violations.map((v) => <li key={v}>{v}</li>)}
          </ul>
        </div>
        <button type="button" onClick={onClose} className="rounded-md border border-white/10 px-2 py-1 text-[11px] text-white/60 hover:bg-white/10 hover:text-white">Dismiss</button>
      </div>
    </motion.section>
  )
}
