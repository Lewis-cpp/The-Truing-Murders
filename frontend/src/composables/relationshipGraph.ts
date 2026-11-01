// The chart option for the relationship graph: exactly the server projection, nothing else.
import type { EChartsOption } from 'echarts'
import type { RelationshipGraph } from '../api/types'

export function graphOption(graph: RelationshipGraph): EChartsOption {
  const series = {
    type: 'graph',
    layout: 'circular',
    circular: { rotateLabel: true },
    // Only what the backend projected: no invented nodes, edges or styling sources.
    data: graph.nodes.map((node) => ({ id: node.character_id, name: node.name })),
    links: graph.edges.map((edge) => ({
      source: edge.from_character_id,
      target: edge.to_character_id,
      value: edge.relationship_type,
      lineStyle: {
        type:
          edge.assertion_kind === 'TESTIMONY' || edge.credibility === 'UNVERIFIED'
            ? 'dashed'
            : 'solid',
      },
    })),
    label: { show: true },
    roam: true,
  }
  return { series: [series] } as EChartsOption
}
