<script setup lang="ts">
import { computed } from 'vue'
import { ElButton, ElCard, ElTable, ElTableColumn, ElTag } from 'element-plus'
import { useGameStore } from '../../stores/game'

const game = useGameStore()
const review = computed(() => game.review!)
const categories = {
  CORRECT: { text: '正确', type: 'success' },
  PARTIALLY_CORRECT: { text: '部分正确', type: 'warning' },
  INCORRECT: { text: '错误', type: 'danger' },
} as const
const verdict = computed(() => review.value.accusation.verdict)
</script>

<template>
  <ElCard header="结案复盘">
    <h2>
      <ElTag :type="categories[verdict.category].type" size="large">
        {{ categories[verdict.category].text }}
      </ElTag>
      {{ verdict.score }} / {{ verdict.max_score }}
    </h2>
    <ElTable :data="verdict.criteria" size="small">
      <ElTableColumn prop="label" label="评分项" width="120" />
      <ElTableColumn label="得分" width="120">
        <template #default="{ row }">{{ row.score }} / {{ row.max_score }}</template>
      </ElTableColumn>
      <ElTableColumn prop="explanation" label="依据" />
    </ElTable>
    <h3>案情真相</h3>
    <p>{{ review.truth.explanation }}</p>
    <h3 v-if="review.missed_evidence.length">遗漏的证据（复盘展示，不补入背包）</h3>
    <ul>
      <li v-for="item in review.missed_evidence" :key="item.evidence_id">
        {{ item.evidence_id }} · {{ item.name }}：{{ item.content }}
      </li>
    </ul>
    <ElButton
      v-if="game.view?.session.phase === 'REVIEW'"
      type="primary"
      :disabled="game.busy"
      @click="game.finish()"
    >
      结束复盘
    </ElButton>
  </ElCard>
</template>
