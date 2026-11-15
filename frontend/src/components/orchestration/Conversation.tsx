import { motion } from 'framer-motion'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { api } from '../../api'
import { tractorColor } from '../../theme'
import type { AgentMessage, MessagePhase } from '../../types'
import { ArrowRightIcon, ChatIcon } from '../Icons'
import { SourceBadge } from '../Panels'
import { inputCls } from '../tools/shared'

const EVERYONE = 'all'
const MAX_STAGGER_S = 1.2
const STAGGER_STEP_S = 0.025

const AGENT: Record<string, { name: string; short: string; color: string }> = {
  fleet_agent: { name: 'Fleet Agent', short: 'F', color: '#7bd88f' },
  navigation_agent: { name: 'Navigation Agent', short: 'N', color: '#f5a3c7' },
  safety_agent: { name: 'Safety Agent', short: 'S', color: '#7dd3fc' },
  all: { name: 'everyone', short: '', color: '#9aa79e' },
}

const agentName = (id: string): string => AGENT[id]?.name ?? id
const agentColor = (id: string): string => AGENT[id]?.color ?? tractorColor(id)
const isTractor = (id: string): boolean => !(id in AGENT)

const PHASES: { id: MessagePhase; title: string; hint: string }[] = [
  { id: 'situation', title: 'Situation', hint: 'What happened, the state of the roads, and where every tractor is' },
  { id: 'auction', title: 'Auction', hint: 'The Fleet Agent calls each job; tractors bid or pass; the winner gets a route and claims it' },
  { id: 'negotiation', title: 'Negotiation', hint: 'Tractors trade jobs between themselves when it improves the plan' },
  { id: 'approval', title: 'Approval', hint: 'The Safety Agent rules on the plan; tractors confirm their queues' },
]

const KIND_LABEL: Record<string, string> = {
  alert: 'alert', status: 'status', announce: 'call', bid: 'bid', decline: 'pass', award: 'award', route: 'route', claim: 'claim',
  no_taker: 'no taker', trade: 'offer', agree: 'agreed', flag: 'flag', verdict: 'verdict', ack: 'confirmed',
}

const KIND_TONE: Record<string, string> = {
  alert: 'bg-alarm/15 text-alarm', decline: 'bg-white/8 text-white/50', no_taker: 'bg-alarm/15 text-alarm', flag: 'bg-alarm/15 text-alarm',
  award: 'bg-leaf/15 text-leaf', claim: 'bg-leaf/15 text-leaf', agree: 'bg-leaf/15 text-leaf', ack: 'bg-leaf/15 text-leaf',
  trade: 'bg-wheat/15 text-wheat', verdict: 'bg-sky-400/15 text-sky-300', route: 'bg-pink-300/15 text-pink-300',
}

/** Messages one agent sent or received, plus the calls it answered so its bids keep their context. */
function messagesOf(messages: AgentMessage[], agent: string): AgentMessage[] {
  if (agent === EVERYONE) return messages
  const own = messages.filter((m) => m.sender === agent || m.to === agent)
  const topics = new Set(own.map((m) => m.topic).filter(Boolean))
  return messages.filter((m) => own.includes(m) || (m.kind === 'announce' && topics.has(m.topic)))
}

function Avatar({ id }: { id: string }) {
  const color = agentColor(id)
  return (
    <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full text-[10px] font-extrabold" style={{ background: `${color}26`, color, boxShadow: `inset 0 0 0 1px ${color}66` }}>
      {AGENT[id]?.short ?? id}
    </span>
  )
}

function MessageRow({ message, delay }: { message: AgentMessage; delay: number }) {
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

function AskAgent({ tractorId, replanIndex }: { tractorId: string; replanIndex: number }) {
  const [question, setQuestion] = useState('')
  const [isBusy, setIsBusy] = useState(false)
  const [reply, setReply] = useState<{ answer: string; source: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const ask = async (event: FormEvent) => {
    event.preventDefault()
    if (!question.trim() || isBusy) return
    setIsBusy(true)
    setError(null)
    try {
      setReply(await api.askAgent(tractorId, question.trim(), replanIndex))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The agent did not answer')
    } finally {
      setIsBusy(false)
    }
  }

  return (
    <div className="mt-2 border-t border-white/8 pt-2">
      <form onSubmit={ask} className="flex gap-2">
        <input value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={300} aria-label={`Question for ${tractorId}`}
          placeholder={`Ask ${tractorId}'s agent about this round, e.g. why did you take that job?`} className={`${inputCls} min-w-0 flex-1`} />
        <button type="submit" disabled={isBusy || !question.trim()}
          className="rounded-md px-3 text-xs font-extrabold text-black disabled:opacity-40" style={{ background: tractorColor(tractorId) }}>{isBusy ? 'Asking…' : `Ask ${tractorId}`}</button>
      </form>
      {error && <p role="alert" className="mt-1.5 text-[12px] text-alarm">{error}</p>}
      {reply && (
        <div className="mt-2 flex gap-2 rounded-lg bg-white/5 px-2 py-1.5">
          <Avatar id={tractorId} />
          <p className="min-w-0 flex-1 text-[12.5px] leading-snug text-white/85">{reply.answer}</p>
          <span className="shrink-0 self-start"><SourceBadge source={reply.source} /></span>
        </div>
      )}
    </div>
  )
}

interface ConversationProps {
  /** Changes with the selected re-plan, so the feed replays its entrance. */
  replanIndex: number
  messages: AgentMessage[]
}

export function Conversation({ replanIndex, messages }: ConversationProps) {
  const [agent, setAgent] = useState(EVERYONE)
  const speakers = [...new Set(messages.map((m) => m.sender))]
  const selected = agent === EVERYONE || speakers.includes(agent) ? agent : EVERYONE
  const shown = messagesOf(messages, selected)

  return (
    <section className="panel flex max-h-[640px] min-h-[320px] flex-col p-3" aria-label="Agent conversation">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-1.5 text-xs font-bold uppercase tracking-widest text-white/60">
          <ChatIcon size={13} className="text-leaf" />Agent conversation
          <span className="rounded-full bg-white/10 px-1.5 py-px font-mono text-[10px] normal-case tracking-normal text-white/60">{shown.length} messages</span>
        </h2>
        <div className="flex flex-wrap gap-1" role="group" aria-label="Listen to one agent">
          {[EVERYONE, ...speakers].map((id) => (
            <button type="button" key={id} aria-pressed={selected === id} onClick={() => setAgent(id)}
              className={`rounded-md border px-2 py-0.5 text-[11px] font-semibold ${selected === id ? 'border-white/30 bg-white/12 text-white' : 'border-white/10 text-white/50 hover:text-white'}`}
              style={selected === id && id !== EVERYONE ? { color: agentColor(id), borderColor: `${agentColor(id)}88` } : undefined}>
              {id === EVERYONE ? 'Everyone' : agentName(id)}
            </button>
          ))}
        </div>
      </div>

      <p className="mt-1.5 text-[11px] leading-snug text-white/45">
        <b className="text-white/65">Recorded trace.</b> Written down step by step while the Fleet Agent searched for this plan. Every number is computed by code; no LLM wrote these messages. Only the answer to &quot;Ask&quot; below comes from the LLM.
      </p>

      <div className="mt-2 min-h-0 flex-1 overflow-y-auto pr-1">
        {PHASES.map((phase, phaseIndex) => {
          const inPhase = shown.filter((m) => m.phase === phase.id)
          if (inPhase.length === 0) return null
          const before = shown.findIndex((m) => m.phase === phase.id)
          return (
            <div key={phase.id} className="mb-3">
              <div className="sticky top-0 z-10 flex items-baseline gap-2 bg-soil-800 py-1">
                <span className="font-mono text-[10px] font-bold text-white/40">{phaseIndex + 1}</span>
                <h3 className="text-[12px] font-extrabold text-white">{phase.title}</h3>
                <span className="text-[11px] text-white/40">{phase.hint}</span>
              </div>
              <ul>
                {inPhase.map((m, i) => (
                  <MessageRow key={`${replanIndex}-${selected}-${phase.id}-${i}`} message={m} delay={Math.min((before + i) * STAGGER_STEP_S, MAX_STAGGER_S)} />
                ))}
              </ul>
            </div>
          )
        })}
        {shown.length === 0 && <p className="py-6 text-center text-sm text-white/40">No messages recorded for this re-plan.</p>}
      </div>

      {isTractor(selected) && selected !== EVERYONE && <AskAgent key={`${selected}-${replanIndex}`} tractorId={selected} replanIndex={replanIndex} />}
    </section>
  )
}
