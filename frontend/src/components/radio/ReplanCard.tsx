import { motion } from 'framer-motion'
import { agentColor } from '../../agents'
import type { RadioItem, ReplanDigest } from '../../radio'
import { clock } from '../../theme'
import { ShieldIcon } from '../Icons'
import { ChangeRow } from '../orchestration/Details'
import { MessageRow } from '../orchestration/MessageRow'

const MAX_CHANGES = 6
const label = 'text-[10px] font-bold uppercase tracking-widest text-white/45'

interface ReplanCardProps {
  item: RadioItem
  replan: ReplanDigest
  /** The messages of this re-plan revealed so far. */
  messages: RadioItem[]
  explanation?: string
  isExpanded: boolean
  onToggle: () => void
}

/** One re-plan in a few lines: what set it off, the plan now, what changed and the verdict. */
export function ReplanCard({ item, replan, messages, explanation, isExpanded, onToggle }: ReplanCardProps) {
  // The opening plan "changes" every job, so listing them adds nothing to the plan itself.
  const changes = replan.isInitial ? replan.changes.filter((c) => c.after === 'unassignable') : replan.changes
  const hidden = Math.max(0, changes.length - MAX_CHANGES)

  return (
    <motion.li initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="mt-3 rounded-xl border border-white/10 bg-black/25 p-3">
      <div className="flex items-baseline gap-2">
        <span className="font-mono text-[10.5px] text-leaf">{clock(item.time)}</span>
        <h3 className="text-[13px] font-extrabold text-white">{item.title}</h3>
      </div>

      {explanation && <p className="mt-1.5 text-[12.5px] leading-snug text-white/80">{explanation}</p>}

      <div className="mt-2">
        <div className={label}>{replan.isInitial ? 'The plan' : 'The plan now'}</div>
        <ul className="mt-1 space-y-0.5 text-[12px]">
          {replan.queues.map((q) => (
            <li key={q.tractorId} className="flex gap-2"><b className="w-6 shrink-0" style={{ color: agentColor(q.tractorId) }}>{q.tractorId}</b><span className="text-white/75">{q.text}</span></li>
          ))}
          {replan.queues.length === 0 && <li className="text-white/45">{replan.isAccepted ? 'No tractor has work queued.' : 'Unchanged: the new plan was vetoed.'}</li>}
        </ul>
      </div>

      {changes.length > 0 && (
        <div className="mt-2">
          <div className={label}>{replan.isInitial ? 'Cannot be done' : 'What changed'}</div>
          <ul>{changes.slice(0, MAX_CHANGES).map((c) => <ChangeRow key={c.job_id} change={c} />)}</ul>
          {hidden > 0 && <p className="mt-1 text-[11px] text-white/40">and {hidden} more</p>}
        </div>
      )}
      {!replan.isInitial && changes.length === 0 && <p className="mt-2 text-[12px] text-white/50">No job changed hands.</p>}

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t border-white/8 pt-2">
        <span className={`flex items-center gap-1.5 text-[11.5px] font-semibold ${replan.isAccepted ? 'text-sky-300' : 'text-alarm'}`}>
          <ShieldIcon size={13} />{replan.isAccepted ? 'Safety Agent approved it' : 'Safety Agent vetoed it'}
        </span>
        <button type="button" onClick={onToggle} aria-expanded={isExpanded}
          className="rounded-md border border-white/12 px-2 py-1 text-[11px] font-semibold text-white/70 hover:bg-white/10 hover:text-white">
          {isExpanded ? 'Hide the conversation' : `Show the conversation (${replan.messageCount} messages)`}
        </button>
      </div>
      {isExpanded && (
        <ul className="mt-2 border-t border-white/8 pt-1">
          {messages.map((m) => m.message && <MessageRow key={m.id} message={m.message} />)}
        </ul>
      )}
    </motion.li>
  )
}
