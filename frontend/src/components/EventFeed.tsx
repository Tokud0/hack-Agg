import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'
import { describeTrigger } from '../labels'
import { clock } from '../theme'
import type { ShiftEvent } from '../shiftEvents'
import { AlertIcon, BoltIcon, ChartIcon, MapIcon, PlusIcon } from './Icons'

const BANNER_MS = 9000

const KIND: Record<string, { label: string; color: string; icon: typeof BoltIcon }> = {
  breakdown: { label: 'Breakdown', color: '#ff5d5d', icon: BoltIcon },
  block_road: { label: 'Road closed', color: '#f5a3c7', icon: MapIcon },
  change_priority: { label: 'Priority changed', color: '#f2c46d', icon: ChartIcon },
  weather: { label: 'Weather', color: '#b9e37a', icon: AlertIcon },
  add_job: { label: 'New job', color: '#7bd88f', icon: PlusIcon },
}
const UNKNOWN = { label: 'Event', color: '#9aa79e', icon: AlertIcon }

/** A large notice over the map when something happens, so nobody has to guess what changed. */
export function EventBanner({ events }: { events: ShiftEvent[] }) {
  const latest = events.at(-1)
  // Events that were already in the log when the page opened are history, not news.
  const seen = useRef(latest?.index ?? -1)
  const [shownIndex, setShownIndex] = useState<number | null>(null)

  useEffect(() => {
    if (!latest || latest.index <= seen.current) {
      if (!latest) seen.current = -1
      return
    }
    seen.current = latest.index
    setShownIndex(latest.index)
    const timer = window.setTimeout(() => setShownIndex(null), BANNER_MS)
    return () => window.clearTimeout(timer)
  }, [latest?.index]) // eslint-disable-line react-hooks/exhaustive-deps -- one notice per event

  const event = events.find((e) => e.index === shownIndex)
  const kind = event ? KIND[String(event.trigger.type)] ?? UNKNOWN : UNKNOWN
  const Icon = kind.icon
  return (
    <AnimatePresence>
      {event && (
        <motion.div key={event.index} role="status" initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -10 }}
          className="pointer-events-auto absolute inset-x-3 top-3 z-20 flex items-start gap-3 rounded-xl border bg-soil-950/95 p-3 shadow-2xl"
          style={{ borderColor: kind.color }}>
          <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg" style={{ background: `${kind.color}26`, color: kind.color }}><Icon size={22} /></span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="text-[10.5px] font-bold uppercase tracking-widest" style={{ color: kind.color }}>{kind.label} · {clock(event.time)}</span>
              {event.isUnprompted && <span className="text-[10.5px] text-white/50">happened by itself, nobody clicked</span>}
            </div>
            <div className="text-[17px] font-extrabold leading-tight text-white">{describeTrigger(event.trigger)}</div>
            <div className="mt-0.5 text-[12.5px] leading-snug text-white/75">{event.outcome ?? 'Re-planning…'}</div>
          </div>
          <button type="button" onClick={() => setShownIndex(null)} className="rounded-md border border-white/10 px-2 py-1 text-[11px] text-white/60 hover:bg-white/10 hover:text-white">Dismiss</button>
        </motion.div>
      )}
    </AnimatePresence>
  )
}

/** The shift's events in order, each with what it did; hover for the detail. */
export function EventTimeline({ events }: { events: ShiftEvent[] }) {
  if (events.length === 0) return null
  return (
    <ul className="flex flex-wrap items-center gap-1.5" aria-label="Events of this shift">
      <li className="text-[10px] font-bold uppercase tracking-widest text-white/45">What happened</li>
      {events.map((event) => {
        const kind = KIND[String(event.trigger.type)] ?? UNKNOWN
        const Icon = kind.icon
        return (
          <li key={event.index} title={event.outcome ?? ''}
            className="flex items-center gap-1.5 rounded-lg border px-2 py-0.5 text-[11.5px] text-white/85" style={{ borderColor: `${kind.color}66`, background: `${kind.color}14` }}>
            <Icon size={12} style={{ color: kind.color }} />
            <span className="font-mono text-[10.5px] text-white/50">{clock(event.time)}</span>
            {describeTrigger(event.trigger)}
          </li>
        )
      })}
    </ul>
  )
}
