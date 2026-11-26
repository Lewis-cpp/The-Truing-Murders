<script setup lang="ts">
import { computed } from 'vue'
import { ElButton, ElCard, ElTag } from 'element-plus'
import { useGameStore } from '../../stores/game'

const game = useGameStore()
const actions = computed(() => game.view?.session.available_actions ?? [])
const states: Record<string, string> = {
  CALM: '平静',
  DEFENSIVE: '戒备',
  NERVOUS: '紧张',
  PRESSURED: '动摇',
  EVADING: '回避中',
  CONFESSION: '已完整承认',
  PARTIAL_CONFESSION: '部分承认',
}
</script>

<template>
  <ElCard header="人物名录">
    <ul data-testid="npc-list" class="npcs">
      <li
        v-for="npc in game.view?.npcs"
        :key="npc.npc_id"
        class="npc"
        :data-testid="`npc-${npc.npc_id}`"
      >
        <strong>{{ npc.name }}</strong> · {{ npc.public_identity }}
        <ElTag size="small">{{ states[npc.display_state] ?? npc.display_state }}</ElTag>
        <ElButton
          v-if="!npc.is_active"
          size="small"
          :data-testid="`talk-${npc.npc_id}`"
          :disabled="!actions.includes('SET_INTERROGATION') || game.busy"
          @click="game.talk(npc.npc_id)"
        >
          审讯
        </ElButton>
      </li>
    </ul>
  </ElCard>
</template>

<style scoped>
.npcs {
  list-style: none;
  padding: 0;
  display: grid;
  gap: 8px;
}
</style>
