<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElButton, ElTag } from 'element-plus'
import { useGameStore } from '../../stores/game'
import { useStageStore, type DossierTab } from '../../stores/stage'

const game = useGameStore()
const stage = useStageStore()
const session = computed(() => game.view!.session)
const phases: Record<string, string> = {
  INVESTIGATION: '调查',
  DEEP_INVESTIGATION: '深入调查',
  INTERROGATION: '审讯',
  ACCUSATION: '指控',
  REVIEW: '复盘',
  FINISHED: '已结束',
}
const savedAt = computed(() => new Date(session.value.saved_at).toLocaleString('zh-CN'))
const scenes = computed(() =>
  (game.view?.scenes ?? []).map((scene) => ({
    id: scene.scene_id,
    name: scene.name,
    // Rooms not investigated yet carry the amber dot.
    fresh: !scene.visited,
    done: scene.actions.filter((action) => action.completed).length,
    total: scene.actions.length,
  })),
)
const dossierTabs = computed<{ id: DossierTab; label: string }[]>(() => [
  { id: 'evidence', label: `证物 ${game.view?.evidence.length ?? 0}` },
  { id: 'suspects', label: `人物 ${game.view?.npcs.length ?? 0}` },
  { id: 'board', label: '关系与时间线' },
])
const caseInfo = computed(
  () =>
    game.cases.find(
      (c) => c.case_id === session.value.case_id && c.case_version === session.value.case_version,
    ) ?? game.cases[0],
)
// Restarting asks twice: the first click reveals the real confirm button.
const restartArmed = ref(false)

function confirmRestart() {
  const target = caseInfo.value
  restartArmed.value = false
  if (target) void game.restart(target)
}
</script>

<template>
  <header class="hud tm-panel">
    <div>
      <p class="eyebrow">THE TRUING MURDERS</p>
      <h1>{{ session.title }}</h1>
      <p class="meta">
        <ElTag data-testid="phase">{{ phases[session.phase] }}</ElTag>
        已自动保存于 {{ savedAt }} · 存档版本 {{ session.state_version }}
      </p>
      <nav v-if="stage.mode === 'scene'" class="scene-tabs" aria-label="已开放场景">
        <button
          v-for="scene in scenes"
          :key="scene.id"
          type="button"
          class="scene-tab"
          :data-testid="`scene-tab-${scene.id}`"
          :aria-pressed="stage.sceneId === scene.id"
          @click="stage.showScene(scene.id)"
        >
          {{ scene.name }} {{ scene.done }}/{{ scene.total }}
          <template v-if="scene.fresh">
            <span class="dot" aria-hidden="true" />
            <span class="sr-only">（未调查）</span>
          </template>
        </button>
      </nav>
    </div>
    <div class="hud-actions">
      <ElButton
        v-for="tab in dossierTabs"
        :key="tab.id"
        :data-testid="`dossier-${tab.id}`"
        :aria-expanded="stage.dossier === tab.id"
        aria-controls="dossier"
        @click="stage.toggleDossier(tab.id)"
      >
        {{ tab.label }}
      </ElButton>
      <ElButton
        v-if="stage.mode === 'scene' || stage.mode === 'interrogation'"
        type="danger"
        plain
        data-testid="open-accusation"
        :disabled="game.busy || !session.available_actions.includes('OPEN_ACCUSATION')"
        @click="game.openAccusation()"
      >
        进入指控
      </ElButton>
      <template v-if="caseInfo">
        <ElButton
          v-if="!restartArmed"
          data-testid="restart-game"
          :disabled="game.busy"
          @click="restartArmed = true"
        >
          重开
        </ElButton>
        <ElButton
          v-else
          type="danger"
          data-testid="confirm-restart"
          :disabled="game.busy"
          @click="confirmRestart"
        >
          确认重开（旧局保留为只读）
        </ElButton>
      </template>
    </div>
  </header>
</template>
