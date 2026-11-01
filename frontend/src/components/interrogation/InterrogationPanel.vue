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
const states: Record<string, string> = {
  CALM: '平静',
  DEFENSIVE: '戒备',
  NERVOUS: '紧张',
  PRESSURED: '动摇',
  EVADING: '回避中',
  CONFESSION: '已完整承认',
  PARTIAL_CONFESSION: '部分承认',
}
const PENDING_ROUNDS = ['PREPARING', 'GENERATING']
// Why a round fell back to the fixed reply; shown next to it, never as an error of the player.
const FALLBACK_REASONS: Record<string, string> = {
  MODEL_TIMEOUT: '模型超时',
  MODEL_RATE_LIMITED: '模型限流',
  MODEL_UNAVAILABLE: '模型暂不可用',
  MODEL_OUTPUT_REJECTED: '生成内容未通过检查',
  CONTEXT_BUDGET_EXCEEDED: '超出本轮上下文预算',
  GENERATION_INTERRUPTED: '生成被中断',
  GENERATION_BUDGET_EXHAUSTED: '本局生成额度已用完',
}

function isPending(round: { generation_status: string }): boolean {
  return PENDING_ROUNDS.includes(round.generation_status)
}

// The newest fallback of this person; older ones stay in the transcript as history.
const fallbackRound = computed(() => {
  const rounds = game.conversations.filter(
    (round) =>
      round.generation_status === 'FALLBACK' && round.fallback_reason !== 'GENERATION_DISABLED',
  )
  return rounds.at(-1) ?? null
})

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
  <ElCard header="人物与审讯">
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
          :disabled="!actions.includes('SET_INTERROGATION') || game.busy"
          @click="game.talk(npc.npc_id)"
        >
          审讯
        </ElButton>
      </li>
    </ul>
    <div v-if="active" data-testid="interrogation-panel" class="panel">
      <blockquote class="statement">{{ active.name }}：{{ active.fixed_statement }}</blockquote>
      <div data-testid="conversation-log" class="log">
        <article v-for="round in game.conversations" :key="round.conversation_id" class="round">
          <p
            v-for="message in round.messages"
            :key="message.message_id"
            :class="message.speaker === 'PLAYER' ? 'player' : 'npc-line'"
          >
            <template v-if="message.speaker === 'PLAYER'">你：{{ message.content }}</template>
            <template v-else>{{ active.name }}：{{ message.content }}</template>
          </p>
          <p v-if="isPending(round)" class="pending">回复准备中</p>
        </article>
      </div>
      <template v-if="fallbackRound">
        <ElAlert
          data-testid="fallback-notice"
          type="warning"
          :title="`已使用固定回复（${FALLBACK_REASONS[fallbackRound.fallback_reason ?? ''] ?? '生成未成功'}）`"
          :closable="false"
          show-icon
        />
        <ElButton
          v-if="fallbackRound.can_retry_reply"
          data-testid="retry-reply"
          size="small"
          :disabled="game.busy"
          @click="game.retryReply(fallbackRound.conversation_id)"
        >
          重试生成
        </ElButton>
      </template>
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
          :data-testid="`topic-${topic.topic_id}`"
          size="small"
          :disabled="game.busy || !actions.includes('ASK_TOPIC')"
          @click="game.askTopic(active.npc_id, topic.topic_id)"
        >
          {{ topic.label }}{{ topic.asked ? '（已问）' : '' }}
        </ElButton>
      </div>
      <div class="row">
        <ElInput
          v-model="question"
          data-testid="chat-input"
          maxlength="2000"
          placeholder="提问（本版本只返回固定说法）"
        />
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
    </div>
  </ElCard>
</template>

<style scoped>
.npcs {
  list-style: none;
  padding: 0;
  display: grid;
  gap: 8px;
}
.panel {
  margin-top: 12px;
  display: grid;
  gap: 10px;
}
.log {
  display: grid;
  gap: 6px;
}
.round + .round {
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 6px;
}
.player {
  color: var(--el-text-color-secondary);
}
.pending {
  color: var(--el-text-color-secondary);
  font-style: italic;
}
.statement {
  margin: 0;
  padding: 8px 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
}
.row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  margin: 0;
}
</style>
