<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { ElButton } from 'element-plus'
import { useStageStore, type DossierTab } from '../../stores/stage'
import EvidencePanel from '../evidence/EvidencePanel.vue'
import SuspectRoster from './SuspectRoster.vue'
import CaseBoard from '../reasoning/CaseBoard.vue'

const stage = useStageStore()
const tabs: { id: DossierTab; label: string }[] = [
  { id: 'evidence', label: '证物与证词' },
  { id: 'suspects', label: '人物' },
  { id: 'board', label: '关系与时间线' },
]
const el = ref<HTMLElement | null>(null)
// Opening moves focus into the drawer; closing hands it back to what opened it.
let returnTo: HTMLElement | null = null

watch(
  () => stage.dossier,
  (now, before) => {
    if (now && !before) {
      returnTo = document.activeElement as HTMLElement | null
      void nextTick(() => el.value?.focus())
    } else if (!now && before) {
      if (returnTo?.isConnected) returnTo.focus()
      returnTo = null
    }
  },
)
</script>

<template>
  <!-- Not modal and always mounted: the stage stays usable beside it (citing evidence
       into the accusation form), and the chart keeps its state between openings. -->
  <Transition name="dossier-slide">
    <aside
      v-show="stage.dossier"
      id="dossier"
      ref="el"
      class="dossier"
      aria-label="侦探卷宗"
      tabindex="-1"
      @keydown.esc="stage.dossier = null"
    >
      <div class="dossier-head">
        <div class="hud-actions">
          <ElButton
            v-for="tab in tabs"
            :key="tab.id"
            :type="stage.dossier === tab.id ? 'primary' : undefined"
            :aria-pressed="stage.dossier === tab.id"
            @click="stage.dossier = tab.id"
          >
            {{ tab.label }}
          </ElButton>
        </div>
        <ElButton data-testid="close-dossier" @click="stage.dossier = null">收起卷宗</ElButton>
      </div>
      <div v-show="stage.dossier === 'evidence'"><EvidencePanel /></div>
      <div v-show="stage.dossier === 'suspects'"><SuspectRoster /></div>
      <div v-show="stage.dossier === 'board'"><CaseBoard /></div>
    </aside>
  </Transition>
</template>
