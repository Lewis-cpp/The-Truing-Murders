<script setup lang="ts">
import { ElCard, ElTag } from 'element-plus'
import { useGameStore } from '../../stores/game'

const game = useGameStore()
</script>

<template>
  <div class="board">
    <ElCard header="人物关系（已确认部分）">
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
        </li>
      </ul>
    </ElCard>
    <ElCard :header="`时间线（${game.view?.timeline.origin_label ?? ''}）`">
      <ul data-testid="timeline-list" class="entries">
        <li
          v-for="item in game.view?.timeline.items"
          :key="item.timeline_event_id"
          :data-testid="`timeline-${item.timeline_event_id}`"
        >
          <strong>{{ item.time_label }}</strong> · {{ item.title }}
          <span class="desc">{{ item.description }}</span>
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
.desc {
  color: var(--el-text-color-secondary);
}
</style>
