// v0.6 acceptance: the chart and timeline only render what the server projected.
import { describe, expect, it } from 'vitest'
import { graphOption } from '../src/composables/relationshipGraph'
import { timelineRows } from '../src/composables/timeline'
import type { RelationshipGraph, TimelineView } from '../src/api/types'

const graph = {
  nodes: [
    {
      character_id: 'NPC01',
      name: '沈砚',
      role: '副研究员',
      public_identity: '副研究员',
    },
    {
      character_id: 'VICTIM',
      name: '陆衡',
      role: '负责人',
      public_identity: '负责人',
    },
    {
      character_id: 'NPC04',
      name: '林澄',
      role: '研究助理',
      public_identity: '研究助理',
    },
  ],
  edges: [
    {
      relationship_id: 'R01',
      from_character_id: 'NPC01',
      to_character_id: 'VICTIM',
      relationship_type: '下属',
      directed: true,
      description: '沈砚是陆衡的下属。',
      assertion_kind: 'FACT',
      source: { kind: 'PUBLIC', id: null, label: '案件公开信息' },
      credibility: 'VERIFIED',
      discovered_at: null,
      known_conflicts: [],
    },
    {
      relationship_id: 'R07',
      from_character_id: 'NPC04',
      to_character_id: 'NPC01',
      relationship_type: '数据质疑',
      directed: true,
      description: '草稿记录。',
      assertion_kind: 'TESTIMONY',
      source: { kind: 'EVIDENCE', id: 'E09', label: '林澄的比对草稿' },
      credibility: 'UNVERIFIED',
      discovered_at: '2026-11-01T00:00:00Z',
      known_conflicts: [],
    },
  ],
} as unknown as RelationshipGraph

const timeline = {
  origin_label: '案发当日 00:00',
  items: [
    {
      timeline_event_id: 'T04',
      title: '走廊回路被手动断开',
      description: '配电日志。',
      scene_id: null,
      participant_ids: [],
      time_precision: 'RANGE',
      time_start_minutes: 1268,
      time_end_minutes: 1278,
      time_label: '21:08—21:18',
      assertion_kind: 'FACT',
      source: { kind: 'EVIDENCE', id: 'E11', label: '电源与校时记录' },
      credibility: 'VERIFIED',
      discovered_at: '2026-11-01T00:00:00Z',
      known_conflicts: [{ kind: 'TIMELINE_EVENT', id: 'T05' }],
    },
    {
      timeline_event_id: 'T05',
      title: '周启称线路自动跳闸',
      description: '周启的说法。',
      scene_id: null,
      participant_ids: ['NPC03'],
      time_precision: 'RANGE',
      time_start_minutes: 1268,
      time_end_minutes: 1278,
      time_label: '停电期间（周启的说法）',
      assertion_kind: 'TESTIMONY',
      source: { kind: 'NPC', id: 'NPC03', label: '周启' },
      credibility: 'UNVERIFIED',
      discovered_at: '2026-11-01T00:00:00Z',
      known_conflicts: [
        { kind: 'TIMELINE_EVENT', id: 'T04' },
        { kind: 'TIMELINE_EVENT', id: 'T99' },
      ],
    },
    {
      timeline_event_id: 'T07',
      title: '沈砚供述袭击陆衡',
      description: '未说明具体分钟。',
      scene_id: 'S01',
      participant_ids: ['NPC01', 'VICTIM'],
      time_precision: 'UNKNOWN',
      time_start_minutes: null,
      time_end_minutes: null,
      time_label: '门禁记录时段内，具体时间未知',
      assertion_kind: 'TESTIMONY',
      source: { kind: 'NPC', id: 'NPC01', label: '沈砚' },
      credibility: 'UNVERIFIED',
      discovered_at: '2026-11-01T00:00:00Z',
      known_conflicts: [],
    },
  ],
} as unknown as TimelineView

describe('relationship graph option', () => {
  it('contains exactly the projected nodes and edges', () => {
    const option = graphOption(graph) as unknown as {
      series: {
        type: string
        data: { id: string; name: string }[]
        links: Record<string, unknown>[]
      }[]
    }
    const [series] = option.series
    expect(series.type).toBe('graph')
    expect(series.data.map((node) => node.id)).toEqual(['NPC01', 'VICTIM', 'NPC04'])
    expect(series.data.map((node) => node.name)).toEqual(['沈砚', '陆衡', '林澄'])
    expect(series.links.map((link) => [link.source, link.target, link.value])).toEqual([
      ['NPC01', 'VICTIM', '下属'],
      ['NPC04', 'NPC01', '数据质疑'],
    ])
    const styles = series.links.map((link) => (link.lineStyle as { type: string }).type)
    expect(styles).toEqual(['solid', 'dashed'])
  })

  it('stays empty for an empty projection', () => {
    const option = graphOption({
      nodes: [],
      edges: [],
    } as unknown as RelationshipGraph) as unknown as {
      series: { data: unknown[]; links: unknown[] }[]
    }
    expect(option.series[0].data).toEqual([])
    expect(option.series[0].links).toEqual([])
  })
})

describe('timeline rows', () => {
  it('keeps order, contradictions and precision without merging anything', () => {
    const rows = timelineRows(timeline)
    expect(rows.map((row) => row.id)).toEqual(['T04', 'T05', 'T07'])
    expect(rows.map((row) => row.timeLabel)).toEqual([
      '21:08—21:18',
      '停电期间（周启的说法）',
      '时间未知：门禁记录时段内，具体时间未知',
    ])
    expect(rows.map((row) => row.badge)).toEqual(['已核验', '证词', '证词'])
    expect(rows[0].conflicts).toEqual(['周启称线路自动跳闸'])
    expect(rows[1].conflicts).toEqual(['走廊回路被手动断开'])
    expect(rows[2].conflicts).toEqual([])
  })
})
