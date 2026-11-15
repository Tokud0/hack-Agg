import { motion } from 'framer-motion'
import { AGENT, agentColor, agentName, EVERYONE } from '../../agents'
import type { AgentMessage } from '../../types'
import { ArrowRightIcon } from '../Icons'

const KIND_LABEL: Record<string, string> = {
  alert: 'alert', status: 'status', announce: 'call', bid: 'bid', decline: 'pass', award: 'award', route: 'route', claim: 'claim',
  no_taker: 'no taker', trade: 'offer', agree: 'agreed', flag: 'flag', verdict: 'verdict', ack: 'confirmed', explain: 'LLM', risk: 'at risk',
}

const KIND_TONE: Record<string, string> = {
  alert: 'bg-alarm/15 text-alarm', decline: 'bg-white/8 text-white/50', no_taker: 'bg-alarm/15 text-alarm', flag: 'bg-alarm/15 text-alarm',
  award: 'bg-leaf/15 text-leaf', claim: 'bg-leaf/15 text-leaf', agree: 'bg-leaf/15 text-leaf', ack: 'bg-leaf/15 text-leaf',
  trade: 'bg-wheat/15 text-wheat', explain: 'bg-wheat/15 text-wheat', risk: 'bg-wheat/15 text-wheat', verdict: 'bg-sky-400/15 text-sky-300', route: 'bg-pink-300/15 text-pink-300',
}

export function Avatar({ id }: { id: string }) {
  const color = agentColor(id)
  return (
    <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full text-[10px] font-extrabold" style={{ background: `${color}26`, color, boxShadow: `inset 0 0 0 1px ${color}66` }}>
      {AGENT[id]?.short ?? id}
    </span>
  )
}

export function MessageRow({ message, delay = 0 }: { message: AgentMessage; delay?: number }) {
  const isCall = message.kind === 'announce'
  const isWinner = message.kind === 'bid' && message.data.is_winner === true
  const isVeto = message.kind === 'verdict' && message.data.accepted === false
  return (
    <motion.li initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay }}
      className={`flex gap-2 rounded-lg px-2 py-1.5 ${isCall ? 'mt-2 bg-white/5' : 'ml-4'} ${isWinner ? 'ring-1 ring-leaf/40' : ''} ${isVeto ? 'ring-1 ring-alarm/50' : ''}`}>
      <Avatar id={message.sender} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5 text-[10.5px] text-white/45">
          <b style={{ color: agentColor(message.sender) }}>{agentName(message.sender)}</b>
          <ArrowRightIcon size={10} />
          <span style={{ color: message.to === EVERYONE ? undefined : agentColor(message.to) }}>{agentName(message.to)}</span>
          {KIND_LABEL[message.kind] && (
            <span className={`rounded px-1 py-px text-[9.5px] font-bold uppercase tracking-wide ${KIND_TONE[message.kind] ?? 'bg-white/8 text-white/60'}`}>{KIND_LABEL[message.kind]}</span>
          )}
          {isWinner && <span className="rounded bg-leaf/15 px-1 py-px text-[9.5px] font-bold uppercase tracking-wide text-leaf">best bid</span>}
        </div>
        <p className={`text-[12.5px] leading-snug ${isCall ? 'font-semibold text-white' : 'text-white/80'}`}>{message.text}</p>
      </div>
    </motion.li>
  )
}
