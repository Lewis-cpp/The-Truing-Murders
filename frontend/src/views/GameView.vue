<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { ElAlert, ElButton, ElPopconfirm, ElSkeleton, ElTag } from 'element-plus'
import { useGameStore } from '../stores/game'
import StartPanel from '../components/game/StartPanel.vue'
import ReviewPanel from '../components/game/ReviewPanel.vue'
import ScenePanel from '../components/investigation/ScenePanel.vue'
import EvidencePanel from '../components/evidence/EvidencePanel.vue'
import InterrogationPanel from '../components/interrogation/InterrogationPanel.vue'
import AccusationForm from '../components/reasoning/AccusationForm.vue'

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

onMounted(game.init)
</script>

<template>
  <main class="game">
    <header class="top">
      <p class="eyebrow">THE TRUING MURDERS · v0.2 固定回复版</p>
      <template v-if="game.view">
        <h1>{{ game.view.session.title }}</h1>
        <p class="meta">
          <ElTag>{{ phases[phase ?? ''] }}</ElTag>
          已自动保存于 {{ savedAt }} · 存档版本 {{ game.view.session.state_version }}
          <ElPopconfirm
            v-if="caseInfo"
            title="重开会创建新的一局，当前进度保留为只读。确定重开？"
            confirm-button-text="重开"
            cancel-button-text="取消"
            @confirm="game.restart(caseInfo)"
          >
            <template #reference>
              <ElButton size="small" :disabled="game.busy">重开</ElButton>
            </template>
          </ElPopconfirm>
        </p>
      </template>
    </header>

    <div v-if="game.error" class="feedback error">
      <ElAlert type="error" :title="game.error" :closable="false" show-icon>
        <ElButton v-if="game.pending" size="small" :loading="game.busy" @click="game.retry()">
          重试同一操作
        </ElButton>
        <ElButton v-else-if="!game.view" size="small" :loading="game.loading" @click="game.init()">
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
      <div v-else class="columns">
        <div>
          <ScenePanel />
          <InterrogationPanel />
          <ElButton
            type="danger"
            plain
            :disabled="
              game.busy || !game.view.session.available_actions.includes('OPEN_ACCUSATION')
            "
            @click="game.openAccusation()"
          >
            进入指控
          </ElButton>
        </div>
        <EvidencePanel />
      </div>
    </template>
  </main>
</template>
