import { motion } from 'framer-motion'
import { clock } from '../../theme'
import { BoltIcon, MenuIcon, PauseIcon, PlayIcon, ResetIcon, ShuffleIcon, SparkIcon, TractorIcon } from '../Icons'

const SHIFT_HOURS = 12

interface TopBarProps {
  scenario: string
  time: number
  isRunning: boolean
  speed: number
  speeds: number[]
  provider: string
  isConnected: boolean
  onTogglePlay: () => void
  onSpeed: (speed: number) => void
  onReset: () => void
  onRandom: () => void
  surprisesLeft: number
  isNavOpen: boolean
  onToggleNav: () => void
}

export function TopBar({ scenario, time, isRunning, speed, speeds, provider, isConnected, onTogglePlay, onSpeed, onReset, onRandom, surprisesLeft, isNavOpen, onToggleNav }: TopBarProps) {
  const shiftShare = Math.min(1, time / SHIFT_HOURS)
  const hasAi = provider !== 'offline'
  return (
    <header className="flex shrink-0 flex-wrap items-center gap-x-6 gap-y-2 border-b border-soil-700 bg-soil-900 px-4 py-2">
      <div className="flex items-center gap-2.5">
        <button type="button" onClick={onToggleNav} aria-pressed={isNavOpen} aria-label={isNavOpen ? 'Hide the menu' : 'Show the menu'} title={isNavOpen ? 'Hide the menu' : 'Show the menu'}
          className="rounded-lg p-2 text-white/55 hover:bg-white/10 hover:text-white"><MenuIcon size={18} /></button>
        <span className="grid h-9 w-9 place-items-center rounded-lg bg-leaf/15 text-leaf"><TractorIcon size={22} /></span>
        <div>
          <div className="text-[15px] font-extrabold leading-tight tracking-tight">RUN THE FLEET</div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-white/45">{scenario}</div>
        </div>
      </div>

      <div className="flex items-center gap-3 rounded-xl bg-black/25 py-1.5 pl-1.5 pr-3">
        <button type="button" onClick={onTogglePlay}
          className="flex w-[92px] items-center justify-center gap-1.5 rounded-lg bg-leaf py-2 text-sm font-extrabold text-black hover:brightness-110">
          {isRunning ? <><PauseIcon size={14} />Pause</> : <><PlayIcon size={14} />Run</>}
        </button>
        <div className="w-[136px]">
          <div className="flex items-baseline justify-between">
            <span className="font-mono text-xl font-bold leading-none text-leaf">{clock(time)}</span>
            <span className="text-[9.5px] uppercase tracking-wider text-white/40">shift time</span>
          </div>
          <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-white/10">
            <motion.div className="h-full bg-leaf" animate={{ width: `${shiftShare * 100}%` }} transition={{ duration: 0.15 }} />
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[9.5px] uppercase tracking-wider text-white/40">Speed</span>
          <div className="flex rounded-lg bg-black/30 p-0.5" role="group" aria-label="Simulation speed">
            {speeds.map((s) => (
              <button type="button" key={s} onClick={() => onSpeed(s)} aria-pressed={speed === s}
                className={`rounded-md px-2 py-1 font-mono text-xs ${speed === s ? 'bg-white/20 text-white' : 'text-white/45 hover:text-white'}`}>{s}x</button>
            ))}
          </div>
        </div>
      </div>

      {surprisesLeft > 0 && (
        <span className="flex items-center gap-1.5 rounded-full bg-alarm/12 px-2.5 py-1 text-[11px] font-semibold text-alarm" title="Breakdowns, closed roads and priority changes that will happen by themselves during this shift">
          <BoltIcon size={11} />{surprisesLeft} surprise event{surprisesLeft === 1 ? '' : 's'} ahead
        </span>
      )}

      <div className="ml-auto flex items-center gap-3">
        <span className={`flex items-center gap-1 rounded-full px-2 py-1 text-[11px] ${hasAi ? 'bg-wheat/15 text-wheat' : 'bg-white/5 text-white/40'}`}>
          <SparkIcon size={11} />{hasAi ? `AI: ${provider}` : 'AI offline'}
        </span>
        <span className="flex items-center gap-1.5 text-[11px] text-white/50">
          <span className={`h-2 w-2 rounded-full ${isConnected ? 'bg-leaf' : 'bg-alarm'}`} />{isConnected ? 'Live' : 'Disconnected'}
        </span>
        <button type="button" onClick={onRandom} title="Start a new shift with random fields, tractors and jobs"
          className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-white/70 hover:bg-white/10 hover:text-white"><ShuffleIcon size={14} />Random shift</button>
        <button type="button" onClick={onReset} title="Start the shift over"
          className="flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-white/70 hover:bg-white/10 hover:text-white"><ResetIcon size={14} />Restart shift</button>
      </div>
    </header>
  )
}
