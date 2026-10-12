<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElButton, ElCard, ElInput, ElOption, ElSelect, ElTag } from 'element-plus'
import { useGameStore } from '../../stores/game'

const game = useGameStore()
const question = ref('')
const evidenceId = ref('')
const actions = computed(() => game.view?.session.available_actions ?? [])
const active = computed(() => game.view?.npcs.find((npc) => npc.is_active) ?? null)
const emotions: Record<string, string> = {
  CALM: '平静',
  DEFENSIVE: '戒备',
  NERVOUS: '紧张',
  PRESSURED: '动摇',
  CONFESSION: '已交代（不代表有罪）',
}

async function ask() {
  if (!active.value || !question.value.trim()) return
  await game.chat(active.value.npc_id, question.value)
  if (!game.error) question.value = ''
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
        <ElButton :disabled="game.busy" @click="game.endTalk()">结束审讯</ElButton>
      </div>
    </template>
  </ElCard>
</template>
