import type { ProposedEvent } from '../../types'

export function describeEvent(e: ProposedEvent): string {
  if (e.type === 'breakdown') return `${e.tractor_id} breaks down`
  if (e.type === 'block_road') return `Road ${e.a}–${e.b} closes`
  if (e.type === 'weather') return `Weather stops ${e.job_type === 'mow' ? 'mowing' : 'spraying'} for ${e.hours} h`
  return `${e.job_id} becomes priority P${e.priority}`
}

export const errorText = (err: unknown): string => (err instanceof Error ? err.message : 'Something went wrong')

export const inputCls =
  'rounded-md border border-white/10 bg-black/30 px-2 py-1.5 text-[12.5px] outline-none focus:border-leaf/60'
