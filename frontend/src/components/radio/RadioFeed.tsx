import { useEffect, useRef, useState } from 'react'
import { agentColor } from '../../agents'
import { explainerId, replanMessagePrefix, type RadioItem, type RadioMode } from '../../radio'
import { clock } from '../../theme'
import { MessageRow } from '../orchestration/MessageRow'
import { Segmented } from '../shell/ViewHeader'
import { ReplanCard } from './ReplanCard'

const MAX_ROWS = 160
/** Keep following the newest message only while the reader is already near the bottom. */
const FOLLOW_WITHIN_PX = 220

const MODES: { id: RadioMode; label: string }[] = [
  { id: 'summary', label: 'Summary' },
  { id: 'all', label: 'All messages' },
]

interface RadioFeedProps {
  items: RadioItem[]
  backlog: number
  mode: RadioMode
  onMode: (mode: RadioMode) => void
}

/** A status call worth a line in the summary: work finished or a stop at the depot. */
const isMilestone = (item: RadioItem): boolean =>
  item.message?.kind === 'status' && item.id.startsWith('log-') && /^(Finished|Refuelling)/.test(item.message.text)

function Milestone({ item }: { item: RadioItem }) {
  if (!item.message) return null
  return (
    <li className="mt-1.5 flex items-baseline gap-2 px-1 text-[11.5px] text-white/55">
      <span className="font-mono text-[10px] text-white/35">{clock(item.time)}</span>
      <b style={{ color: agentColor(item.message.sender) }}>{item.message.sender}</b>{item.message.text}
    </li>
  )
}

/** What the agents say to each other: a summary per re-plan by default, every message on request. */
export function RadioFeed({ items, backlog, mode, onMode }: RadioFeedProps) {
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set())
  const scroller = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = scroller.current
    if (el && el.scrollHeight - el.scrollTop - el.clientHeight < FOLLOW_WITHIN_PX) el.scrollTop = el.scrollHeight
  }, [items.length, mode])

  const toggle = (id: string) => setExpanded((open) => {
    const next = new Set(open)
    if (!next.delete(id)) next.add(id)
    return next
  })

  const explanationOf = (index: number): string | undefined => items.find((i) => i.id === explainerId(index))?.message?.text
  const messagesOf = (index: number): RadioItem[] => items.filter((i) => i.id.startsWith(replanMessagePrefix(index)))
  const summaryRows = items.filter((i) => i.replan || isMilestone(i))

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-widest text-white/60">
          <span className={`h-2 w-2 rounded-full bg-leaf ${backlog ? 'blink' : ''}`} />Agent radio
        </h2>
        <Segmented label="How much to show" options={MODES} value={mode} onChange={onMode} />
      </div>
      <p className="mt-1 text-[11px] leading-snug text-white/45">
        {mode === 'summary'
          ? 'Each plan in a few lines. Switch to All messages to follow the agents talking, here and on the map.'
          : 'Every message, here and on the map. A re-plan is decided in milliseconds; its conversation is the recorded trace, played back slowly.'}
      </p>

      <div ref={scroller} className="mt-1 min-h-0 flex-1 overflow-y-auto pr-1">
        {items.length === 0 && <p className="py-6 text-center text-sm text-white/40">Quiet so far. Press Run.</p>}
        {mode === 'summary' ? (
          <ul>
            {summaryRows.slice(-MAX_ROWS).map((item) => item.replan ? (
              <ReplanCard key={item.id} item={item} replan={item.replan} messages={messagesOf(item.replan.index)} explanation={explanationOf(item.replan.index)}
                isExpanded={expanded.has(item.id)} onToggle={() => toggle(item.id)} />
            ) : <Milestone key={item.id} item={item} />)}
          </ul>
        ) : (
          <ul>
            {items.slice(-MAX_ROWS).map((item) => item.message ? (
              <MessageRow key={item.id} message={item.message} />
            ) : (
              <li key={item.id} className="sticky top-0 z-10 mt-3 flex items-baseline gap-2 border-t border-white/10 bg-soil-900 py-1.5">
                <span className="font-mono text-[10.5px] text-leaf">{clock(item.time)}</span>
                <span className="text-[12px] font-extrabold text-white">{item.title}</span>
                <span className="ml-auto text-[10px] text-white/40">{item.note}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
