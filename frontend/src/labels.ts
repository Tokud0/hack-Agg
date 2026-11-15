export const INVARIANT_LABELS: Record<string, string> = {
  one_tractor_per_job: 'Each job has at most one tractor',
  done_never_reassigned: 'Completed work never reassigned',
  hard_constraints: 'Implement · fuel · deadline respected',
  every_open_job_accounted: 'No work lost: reassigned or flagged',
}

import { clock } from './theme'

export const WORK_NAME: Record<string, string> = { spray: 'spraying', mow: 'mowing' }

export function describeTrigger(trigger: Record<string, string | number>): string {
  switch (trigger.type) {
    case 'initial_plan': return 'Shift start'
    case 'breakdown': return `${trigger.tractor_id} broke down`
    case 'block_road': return `Road ${trigger.a}–${trigger.b} closed`
    case 'change_priority': return `${trigger.job_id} set to P${trigger.priority}`
    case 'weather': {
      const work = WORK_NAME[String(trigger.job_type)] ?? 'work'
      return typeof trigger.until === 'number' ? `Weather: no ${work} until ${clock(trigger.until)}` : `Weather: no ${work} for ${trigger.hours} h`
    }
    case 'add_job': return `New job ${trigger.job_id} on ${trigger.field_id}`
    default: return String(trigger.type)
  }
}
