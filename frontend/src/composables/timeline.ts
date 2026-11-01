// Timeline rows for display: server order preserved, contradictions kept visible.
import type { TimelineView } from '../api/types'

export interface TimelineRow {
  id: string
  title: string
  timeLabel: string
  badge: string
  conflicts: string[]
}

export function timelineRows(timeline: TimelineView): TimelineRow[] {
  const titles = new Map(timeline.items.map((item) => [item.timeline_event_id, item.title]))
  return timeline.items.map((item) => ({
    id: item.timeline_event_id,
    title: item.title,
    timeLabel: item.time_precision === 'UNKNOWN' ? `时间未知：${item.time_label}` : item.time_label,
    badge:
      item.assertion_kind === 'TESTIMONY'
        ? '证词'
        : item.assertion_kind === 'FACT' && item.credibility === 'VERIFIED'
          ? '已核验'
          : '存疑',
    // Only entries that exist in this very view can be named; nothing is merged away.
    conflicts: item.known_conflicts.flatMap((conflict) => {
      const title = titles.get(conflict.id)
      return title ? [title] : []
    }),
  }))
}
