<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElAlert, ElButton, ElCard, ElInput, ElOption, ElSelect, ElTag } from 'element-plus'
import { useGameStore } from '../../stores/game'

const game = useGameStore()
const question = ref('')
const evidenceId = ref('')
const testimonyId = ref('')
const contradictionEvidenceId = ref('')
const actions = computed(() => game.view?.session.available_actions ?? [])
const active = computed(() => game.view?.npcs.find((npc) => npc.is_active) ?? null)
// Only the active NPC's recorded words can be cited; public case facts are not testimony.
const testimony = computed(() =>
  (game.view?.known_information ?? []).filter(
    (info) => info.source.kind === 'NPC' && info.source.id === active.value?.npc_id,
  ),
)
const emotions: Record<string, string> = {
  CALM: '平静',
  DEFENSIVE: '戒备',
  NERVOUS: '紧张',
  PRESSURED: '动摇',
  EVADING: '回避',
  CONFESSION: '已交代（不代表有罪）',
}

async function ask() {
  if (!active.value || !question.value.trim()) return
  await game.chat(active.value.npc_id, question.value)
  if (!game.error) question.value = ''
}

function contradict() {
  if (!active.value || !testimonyId.value || !contradictionEvidenceId.value) return
  return game.contradict(active.value.npc_id, testimonyId.value, contradictionEvidenceId.value)
}
</script>

<template>
  <ElCard header="审讯">
    <div v-for="npc in game.view?.npcs" :key="npc.npc_id" class="npc">
      <strong>{{ npc.name }}</strong> · {{ npc.public_identity }}
      <ElTag size="small">{{ emotions[npc.display_state] ?? npc.display_state }}</ElTag>
      <ElButton
        v-if="!npc.is_active"
        size="small"
        :disabled="!actions.includes('SET_INTERROGATION') || game.busy"
        @click="game.talk(npc.npc_id)"
      >
        审讯
      </ElButton>
    </div>
    <template v-if="active">
      <blockquote class="statement">{{ active.name }}：{{ active.fixed_statement }}</blockquote>
      <p v-for="(reply, index) in game.replies" :key="index" class="reply">
        {{ active.name }}：{{ reply }}
      </p>
      <ElAlert
        v-if="active.is_evading"
        type="warning"
        :title="`${active.name}在回避，暂时问不出什么。结束审讯后再来。`"
        :closable="false"
        show-icon
      />
      <div v-if="active.topics.length" class="row">
        <span>追问：</span>
        <ElButton
          v-for="topic in active.topics"
          :key="topic.topic_id"
          size="small"
          :disabled="game.busy || !actions.includes('ASK_TOPIC')"
          @click="game.askTopic(active.npc_id, topic.topic_id)"
        >
          {{ topic.label }}{{ topic.asked ? '（已问）' : '' }}
        </ElButton>
      </div>
      <div class="row">
        <ElInput v-model="question" maxlength="2000" placeholder="提问（本版本只返回固定说法）" />
        <ElButton :disabled="game.busy || !question.trim()" @click="ask">提问</ElButton>
      </div>
      <div class="row">
        <ElSelect v-model="evidenceId" placeholder="选择要出示的证据" style="width: 260px">
          <ElOption
            v-for="item in game.view?.evidence"
            :key="item.evidence_id"
            :label="`${item.evidence_id} · ${item.name}`"
            :value="item.evidence_id"
          />
        </ElSelect>
        <ElButton
          type="warning"
          :disabled="game.busy || !evidenceId"
          @click="game.present(active.npc_id, evidenceId)"
        >
          出示
        </ElButton>
      </div>
      <div class="row">
        <ElSelect
          v-model="testimonyId"
          placeholder="选择该角色的证词"
          no-data-text="还没有记录该角色的证词"
          style="width: 260px"
        >
          <ElOption
            v-for="info in testimony"
            :key="info.information_ref.id"
            :label="`${info.information_ref.id} · ${info.content}`"
            :value="info.information_ref.id"
          />
        </ElSelect>
        <ElSelect
          v-model="contradictionEvidenceId"
          placeholder="选择与之矛盾的证据"
          style="width: 260px"
        >
          <ElOption
            v-for="item in game.view?.evidence"
            :key="item.evidence_id"
            :label="`${item.evidence_id} · ${item.name}`"
            :value="item.evidence_id"
          />
        </ElSelect>
        <ElButton
          type="warning"
          :disabled="game.busy || !testimonyId || !contradictionEvidenceId"
          @click="contradict"
        >
          指出矛盾
        </ElButton>
      </div>
      <p class="hint">
        出示无关材料或指错矛盾会让对方更戒备；接连这样做，对方会开始回避，直到你结束审讯。
      </p>
      <ElButton :disabled="game.busy" @click="game.endTalk()">结束审讯</ElButton>
    </template>
  </ElCard>
</template>
