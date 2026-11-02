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
  <div data-testid="scene-list">
    <div
      v-for="scene in game.view?.scenes"
      :key="scene.scene_id"
      :data-testid="`scene-${scene.scene_id}`"
    >
      <ElCard :header="scene.name">
        <p>{{ scene.description }}</p>
        <ul class="actions">
          <li v-for="action in scene.actions" :key="action.action_id">
            <ElTooltip :disabled="!action.disabled_reason" :content="action.disabled_reason ?? ''">
              <span>
                <ElButton
                  :data-testid="`action-${action.action_id}`"
                  :data-completed="action.completed ? 'true' : undefined"
                  :disabled="!canInvestigate || !action.enabled || game.busy"
                  @click="game.investigate(scene.scene_id, action.action_id)"
                >
                  {{ action.label }}
                </ElButton>
              </span>
            </ElTooltip>
            <ElTag v-if="action.completed" type="success" size="small">已调查</ElTag>
            <span v-if="action.disabled_reason" class="reason">{{ action.disabled_reason }}</span>
          </li>
        </ul>
      </ElCard>
    </div>
  </div>
</template>

<style scoped>
.actions {
  list-style: none;
  padding: 0;
  display: grid;
  gap: 8px;
}
.reason {
  color: var(--tm-text-muted, #5f6672);
  font-size: 12px;
  margin-left: 8px;
}
</style>
