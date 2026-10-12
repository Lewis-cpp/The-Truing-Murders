<script setup lang="ts">
import { computed } from 'vue'
import { ElButton, ElCard, ElTag, ElTooltip } from 'element-plus'
import { useGameStore } from '../../stores/game'

const game = useGameStore()
const canInvestigate = computed(
  () => game.view?.session.available_actions.includes('INVESTIGATE') ?? false,
)
</script>

<template>
  <ElCard v-for="scene in game.view?.scenes" :key="scene.scene_id" :header="scene.name">
    <p>{{ scene.description }}</p>
    <ul class="actions">
      <li v-for="action in scene.actions" :key="action.action_id">
        <ElTooltip :disabled="!action.disabled_reason" :content="action.disabled_reason ?? ''">
          <span>
            <ElButton
              :disabled="!canInvestigate || !action.enabled || game.busy"
              @click="game.investigate(scene.scene_id, action.action_id)"
            >
              {{ action.label }}
            </ElButton>
          </span>
        </ElTooltip>
        <ElTag v-if="action.completed" type="success" size="small">已调查</ElTag>
      </li>
    </ul>
  </ElCard>
</template>
