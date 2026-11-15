export const TRACTOR_COLORS: Record<string, string> = {
  T1: '#f2c46d',
  T2: '#5cc8ff',
  T3: '#c792ea',
  T4: '#ff9e64',
}

export const tractorColor = (id: string | null | undefined): string =>
  (id && TRACTOR_COLORS[id]) || '#9aa79e'

export const SHIFT_START_HOUR = 6

export function clock(hours: number): string {
  const total = Math.max(0, Math.round((SHIFT_START_HOUR + hours) * 60))
  const h = Math.floor(total / 60) % 24
  const m = total % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

export const PRIORITY_STYLE: Record<number, string> = {
  1: 'bg-alarm/20 text-alarm border-alarm/40',
  2: 'bg-wheat/15 text-wheat border-wheat/40',
  3: 'bg-white/5 text-white/60 border-white/15',
}
