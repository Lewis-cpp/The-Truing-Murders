<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElAlert, ElButton, ElSkeleton, ElTag } from 'element-plus'
import { useGameStore } from '../stores/game'
import StartPanel from '../components/game/StartPanel.vue'
import ReviewPanel from '../components/game/ReviewPanel.vue'
import ScenePanel from '../components/investigation/ScenePanel.vue'
import EvidencePanel from '../components/evidence/EvidencePanel.vue'
import InterrogationPanel from '../components/interrogation/InterrogationPanel.vue'
import AccusationForm from '../components/reasoning/AccusationForm.vue'
import CaseBoard from '../components/reasoning/CaseBoard.vue'

const game = useGameStore()
const phase = computed(() => game.view?.session.phase)
const phases: Record<string, string> = {
  INVESTIGATION: '调查',
  DEEP_INVESTIGATION: '深入调查',
  INTERROGATION: '审讯',
  ACCUSATION: '指控',
  REVIEW: '复盘',
  FINISHED: '已结束',
}
const savedAt = computed(() =>
  game.view ? new Date(game.view.session.saved_at).toLocaleString('zh-CN') : '',
)
const caseInfo = computed(
  () =>
    game.cases.find(
      (c) =>
        c.case_id === game.view?.session.case_id &&
        c.case_version === game.view?.session.case_version,
    ) ?? game.cases[0],
)
// Restarting asks twice: the first click reveals the real confirm button.
const restartArmed = ref(false)

// Below 768px the workbench becomes a single column with tabs; the default tab is
// the scenes column and entering an interrogation switches to it automatically.
const TABS = [
  { id: 'scenes', label: '场景与证据' },
  { id: 'interrogation', label: '审讯' },
  { id: 'board', label: '关系与时间线' },
] as const
const activeTab = ref<(typeof TABS)[number]['id']>('scenes')
const isNarrow = ref(window.innerWidth < 768)
function onResize() {
  isNarrow.value = window.innerWidth < 768
}
onMounted(() => window.addEventListener('resize', onResize))
onUnmounted(() => window.removeEventListener('resize', onResize))
watch(
  () => [game.view?.session.phase, game.view?.session.active_npc_id] as const,
  ([phase, activeNpc]) => {
    if (isNarrow.value && phase === 'INTERROGATION' && activeNpc) activeTab.value = 'interrogation'
  },
)

function confirmRestart() {
  const target = caseInfo.value
  restartArmed.value = false
  if (target) void game.restart(target)
}

onMounted(game.init)
// Leaving the page stops the polling; a reload rebuilds it from the pending rounds.
onUnmounted(() => game.stopPolling())
</script>

<template>
  <main class="game">
    <header class="top">
      <p class="eyebrow">THE TRUING MURDERS · 全案固定回复版</p>
      <template v-if="game.view">
        <h1>{{ game.view.session.title }}</h1>
        <p class="meta">
          <ElTag data-testid="phase">{{ phases[phase ?? ''] }}</ElTag>
          已自动保存于 {{ savedAt }} · 存档版本 {{ game.view.session.state_version }}
          <template v-if="caseInfo">
            <ElButton
              v-if="!restartArmed"
              size="small"
              data-testid="restart-game"
              :disabled="game.busy"
              @click="restartArmed = true"
            >
              重开
            </ElButton>
            <ElButton
              v-else
              size="small"
              type="danger"
              data-testid="confirm-restart"
              :disabled="game.busy"
              @click="confirmRestart"
            >
              确认重开（旧局保留为只读）
            </ElButton>
          </template>
        </p>
      </template>
    </header>

    <!-- In ACCUSATION the form renders the rejection itself, next to the fields it belongs to. -->
    <div v-if="game.error && phase !== 'ACCUSATION'" class="feedback error" role="alert">
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
      <p class="intro">{{ game.view.intro_text }}</p>
      <ReviewPanel v-if="game.review" />
      <AccusationForm v-else-if="phase === 'ACCUSATION'" />
      <template v-else>
        <div v-if="isNarrow" class="tabs" role="tablist" aria-label="工作台分区">
          <button
            v-for="tab in TABS"
            :key="tab.id"
            role="tab"
            :aria-selected="activeTab === tab.id"
            class="tab"
            :class="{ active: activeTab === tab.id }"
            @click="activeTab = tab.id"
          >
            {{ tab.label }}
          </button>
        </div>
        <div class="columns" :data-active-tab="isNarrow ? activeTab : undefined">
          <div class="col col-scenes" :class="{ hidden: isNarrow && activeTab !== 'scenes' }">
            <ScenePanel />
            <EvidencePanel />
          </div>
          <div
            class="col col-interrogation"
            :class="{ hidden: isNarrow && activeTab !== 'interrogation' }"
          >
            <!-- A new game must not inherit the last game's selections. -->
            <InterrogationPanel :key="game.view.session.session_id" />
            <ElButton
              type="danger"
              plain
              data-testid="open-accusation"
              :disabled="
                game.busy || !game.view.session.available_actions.includes('OPEN_ACCUSATION')
              "
              @click="game.openAccusation()"
            >
              进入指控
            </ElButton>
          </div>
          <div class="col col-board" :class="{ hidden: isNarrow && activeTab !== 'board' }">
            <CaseBoard />
          </div>
        </div>
      </template>
    </template>
  </main>
</template>
