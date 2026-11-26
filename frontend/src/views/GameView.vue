<script setup lang="ts">
import { onMounted, onUnmounted, watch } from 'vue'
import { ElAlert, ElButton, ElSkeleton } from 'element-plus'
import { useGameStore } from '../stores/game'
import { useStageStore } from '../stores/stage'
import StartPanel from '../components/game/StartPanel.vue'
import ReviewPanel from '../components/game/ReviewPanel.vue'
import ScenePanel from '../components/investigation/ScenePanel.vue'
import InterrogationPanel from '../components/interrogation/InterrogationPanel.vue'
import AccusationForm from '../components/reasoning/AccusationForm.vue'
import StageBackdrop from '../components/stage/StageBackdrop.vue'
import StageHud from '../components/stage/StageHud.vue'
import DossierDrawer from '../components/stage/DossierDrawer.vue'

const game = useGameStore()
const stage = useStageStore()

// Starting an interrogation from the roster hands the whole stage to it.
watch(
  () => game.view?.session.active_npc_id,
  (npcId) => {
    if (npcId) stage.dossier = null
  },
)

onMounted(game.init)
// Leaving the page stops the polling; a reload rebuilds it from the pending rounds.
onUnmounted(() => game.stopPolling())
</script>

<template>
  <main class="game">
    <StageBackdrop />
    <StageHud v-if="game.view" />

    <!-- In ACCUSATION the form renders the rejection itself, next to the fields it belongs to. -->
    <div v-if="game.error && stage.mode !== 'accusation'" class="feedback error" role="alert">
      <ElAlert type="error" :title="game.error" :closable="false" show-icon>
        <ElButton v-if="game.pending" size="small" :loading="game.busy" @click="game.retry()">
          重试同一操作
        </ElButton>
        <ElButton
          v-else-if="!game.view || game.stale"
          size="small"
          :loading="game.loading"
          @click="game.init()"
        >
          重新加载
        </ElButton>
      </ElAlert>
    </div>
    <div v-if="game.unsupported" class="feedback">
      <ElAlert
        type="warning"
        title="当前版本暂时无法读取此存档"
        description="存档已保留，不会被自动重置。可以在下方开始新的一局，或联系维护者升级后再继续。"
        :closable="false"
        show-icon
      />
    </div>
    <div class="feedback" role="status" aria-live="polite">
      <ElAlert
        v-if="game.notice"
        :type="game.notice.kind"
        :title="game.notice.text"
        :closable="false"
      />
    </div>

    <ElSkeleton v-if="game.loading" :rows="6" animated />
    <StartPanel v-else-if="!game.view && !game.error" />
    <template v-else-if="game.view">
      <ReviewPanel v-if="stage.mode === 'review'" />
      <AccusationForm v-else-if="stage.mode === 'accusation'" />
      <!-- A new game must not inherit the last game's selections. -->
      <InterrogationPanel
        v-else-if="stage.mode === 'interrogation'"
        :key="game.view.session.session_id"
      />
      <div v-else class="stage-scene">
        <p class="intro tm-panel">{{ game.view.intro_text }}</p>
        <ScenePanel />
      </div>
      <DossierDrawer />
    </template>
  </main>
</template>
