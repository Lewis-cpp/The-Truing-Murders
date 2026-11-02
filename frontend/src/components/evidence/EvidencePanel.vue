<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { ElButton, ElCard, ElEmpty, ElTag } from 'element-plus'
import { useGameStore } from '../../stores/game'
import type { EvidenceView } from '../../api/types'

const game = useGameStore()
const selectedId = ref<string | null>(null)
const selected = computed(
  () => game.view?.evidence.find((item) => item.evidence_id === selectedId.value) ?? null,
)
// Opening moves focus into the detail; closing hands it back to the trigger button.
const detailEl = ref<HTMLElement | null>(null)
const trigger = ref<HTMLButtonElement | null>(null)

function open(item: EvidenceView, event: Event) {
  trigger.value = event.currentTarget as HTMLButtonElement
  selectedId.value = item.evidence_id
  void nextTick(() => detailEl.value?.focus())
}

function close() {
  selectedId.value = null
  trigger.value?.focus()
  trigger.value = null
}
</script>

<template>
  <div>
    <ElCard header="证据背包">
      <ElEmpty v-if="!game.view?.evidence.length" description="尚未取得证据。" :image-size="60" />
      <ul data-testid="evidence-list" class="bag">
        <li v-for="item in game.view?.evidence" :key="item.evidence_id">
          <button
            class="entry"
            :data-testid="`evidence-${item.evidence_id}`"
            @click="open(item, $event)"
          >
            {{ item.evidence_id }} · {{ item.name }}
          </button>
          <ElTag size="small" :type="item.credibility === 'VERIFIED' ? 'success' : 'warning'">
            {{ item.credibility === 'VERIFIED' ? '已核验' : '未核验' }}
          </ElTag>
          <ElTag v-if="item.key_badge" size="small" type="danger">关键</ElTag>
        </li>
      </ul>
    </ElCard>
    <ElCard header="证词记录">
      <ElEmpty
        v-if="!game.view?.known_information.length"
        description="还没有记录任何证词。"
        :image-size="60"
      />
      <article
        v-for="info in game.view?.known_information"
        :key="info.information_ref.id"
        class="evidence"
      >
        <h3>
          {{ info.information_ref.id }} · 证词 · {{ info.source.label }}
          <ElTag size="small" type="warning">未经核验</ElTag>
        </h3>
        <p>{{ info.content }}</p>
      </article>
    </ElCard>
    <ElCard v-if="selected" header="证据详情">
      <div data-testid="evidence-detail" ref="detailEl" tabindex="-1">
        <h3>{{ selected.evidence_id }} · {{ selected.name }}</h3>
        <p>{{ selected.content }}</p>
        <p class="source">来源：{{ selected.source.label }}</p>
        <ElButton size="small" data-testid="close-evidence-detail" @click="close">
          关闭详情
        </ElButton>
      </div>
    </ElCard>
  </div>
</template>

<style scoped>
.bag {
  list-style: none;
  padding: 0;
  display: grid;
  gap: 8px;
}
.entry {
  border: none;
  background: none;
  cursor: pointer;
  padding: 0;
  font: inherit;
  color: var(--el-color-primary);
  margin-right: 8px;
}
.evidence + .evidence {
  margin-top: 12px;
}
.source {
  color: var(--tm-text-muted, #5f6672);
  font-size: 12px;
}
</style>
