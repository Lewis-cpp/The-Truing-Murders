<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import * as echarts from 'echarts/core'
import { GraphChart } from 'echarts/charts'
import { SVGRenderer } from 'echarts/renderers'
import { ElButton, ElCard, ElTag } from 'element-plus'
import { useGameStore } from '../../stores/game'
import { graphOption } from '../../composables/relationshipGraph'
import { timelineRows, type TimelineRow } from '../../composables/timeline'
import type { TimelineItem } from '../../api/types'

echarts.use([GraphChart, SVGRenderer])

const game = useGameStore()
const chartEl = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

interface DisplayRow extends TimelineRow {
  description: string
  source: { kind: string; id: string | null; label: string }
}

const rows = computed<DisplayRow[]>(() => {
  const view = game.view?.timeline ?? { origin_label: '', items: [] as TimelineItem[] }
  const items = new Map(view.items.map((item) => [item.timeline_event_id, item]))
  return timelineRows(view).map((row) => {
    const item = items.get(row.id)
    return {
      ...row,
      description: item?.description ?? '',
      source: item?.source ?? { kind: '', id: null, label: '' },
    }
  })
})

function evidenceHeld(evidenceId: string | null): boolean {
  return (
    evidenceId != null &&
    (game.view?.evidence ?? []).some((item) => item.evidence_id === evidenceId)
  )
}

function canCite(source: { kind: string; id: string | null }): boolean {
  return (
    game.view?.session.phase === 'ACCUSATION' &&
    source.kind === 'EVIDENCE' &&
    evidenceHeld(source.id)
  )
}

function renderGraph() {
  const el = chartEl.value
  if (!el || !game.view) return
  // A zero-size container (hidden tab, jsdom) cannot host a chart; skip and let a
  // later resize/watch trigger the render instead of erroring inside the renderer.
  if (el.clientWidth === 0 || el.clientHeight === 0) return
  if (!chart) {
    chart = echarts.init(el, undefined, { renderer: 'svg' })
  }
  chart.setOption(graphOption(game.view.relationships))
}

function resizeChart() {
  chart?.resize()
}

onMounted(() => {
  void nextTick(renderGraph)
  window.addEventListener('resize', resizeChart)
})
watch(
  () => game.view?.relationships,
  () => void nextTick(renderGraph),
  { deep: true },
)
onUnmounted(() => {
  window.removeEventListener('resize', resizeChart)
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div class="board">
    <ElCard header="人物关系（已确认部分）">
      <!-- The chart and the text list show the same projection; neither replaces the other. -->
      <div ref="chartEl" data-testid="relationship-graph" class="graph" />
      <ul data-testid="relationship-list" class="entries">
        <li
          v-for="edge in game.view?.relationships.edges"
          :key="edge.relationship_id"
          :data-testid="`relationship-${edge.relationship_id}`"
        >
          {{ edge.description }}
          <ElTag size="small" :type="edge.credibility === 'VERIFIED' ? 'success' : 'warning'">
            {{ edge.credibility === 'VERIFIED' ? '已核验' : '证词' }}
          </ElTag>
          <ElButton
            v-if="canCite(edge.source)"
            :data-testid="`cite-${edge.source.id}`"
            size="small"
            :disabled="game.busy"
            @click="game.citeEvidence(edge.source.id!)"
          >
            引用 {{ edge.source.label }}
          </ElButton>
        </li>
      </ul>
    </ElCard>
    <ElCard :header="`时间线（${game.view?.timeline.origin_label ?? ''}）`">
      <ul data-testid="timeline-list" class="entries">
        <li v-for="row in rows" :key="row.id" :data-testid="`timeline-${row.id}`">
          <strong>{{ row.timeLabel }}</strong> · {{ row.title }}
          <ElTag size="small" :type="row.badge === '已核验' ? 'success' : 'warning'">
            {{ row.badge }}
          </ElTag>
          <span class="desc">{{ row.description }}</span>
          <span v-if="row.conflicts.length" class="conflict">
            与{{ row.conflicts.join('、') }}矛盾
          </span>
          <ElButton
            v-if="canCite(row.source)"
            :data-testid="`cite-${row.source.id}`"
            size="small"
            :disabled="game.busy"
            @click="game.citeEvidence(row.source.id!)"
          >
            引用该条目的证据
          </ElButton>
        </li>
      </ul>
    </ElCard>
  </div>
</template>

<style scoped>
.board {
  display: grid;
  gap: 12px;
}
.entries {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 8px;
}
.graph {
  width: 100%;
  height: 260px;
}
.desc {
  color: var(--tm-text-muted, #5f6672);
}
.conflict {
  color: var(--el-color-danger);
  font-size: 12px;
}
</style>
