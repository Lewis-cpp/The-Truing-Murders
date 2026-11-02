<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElAlert, ElButton, ElCard, ElInput } from 'element-plus'
import { useGameStore } from '../../stores/game'
import type { AccusationContent } from '../../api/types'

const game = useGameStore()
const options = computed(() => game.view!.accusation_options)
// The draft comes from the server view; editing works on a local copy until it is saved.
// A failed save (version conflict, network) never clears this local copy.
const saved = game.view?.accusation_draft
const form = reactive<AccusationContent>(
  saved
    ? JSON.parse(JSON.stringify(saved))
    : {
        suspect_character_id: null,
        weapon_option_id: null,
        motive_option_id: null,
        ordered_process_step_ids: [],
        cited_evidence_ids: [],
        step_evidence_links: [],
        explanation: '',
      },
)
const confirmed = ref(false)
// Incompleteness is a server-side business rule (ACCUSATION_INCOMPLETE); the checkbox is
// the only client gate so the player can always ask the server to judge a draft.
const label = (id: string) => options.value.process_steps.find((s) => s.id === id)?.label ?? id

// The reasoning board asks the form to cite evidence; drain the queue into the local copy.
watch(
  () => game.citeRequests.slice(),
  (requests) => {
    if (!requests.length) return
    for (const evidenceId of requests) {
      if (!form.cited_evidence_ids.includes(evidenceId)) form.cited_evidence_ids.push(evidenceId)
    }
    game.citeRequests.splice(0, requests.length)
  },
)

function content(): AccusationContent {
  return JSON.parse(JSON.stringify(form))
}

function toggleStep(stepId: string, checked: boolean) {
  const current = form.ordered_process_step_ids
  if (checked && !current.includes(stepId)) {
    // The order is the order of checking; re-checking re-appends at the end.
    form.ordered_process_step_ids = [...current, stepId]
  }
  if (!checked) {
    form.ordered_process_step_ids = current.filter((id) => id !== stepId)
    form.step_evidence_links = form.step_evidence_links.filter((link) => link.step_id !== stepId)
  }
}

function stepChecked(stepId: string): boolean {
  return form.ordered_process_step_ids.includes(stepId)
}

function toggleCited(evidenceId: string, checked: boolean) {
  if (checked && !form.cited_evidence_ids.includes(evidenceId)) {
    form.cited_evidence_ids = [...form.cited_evidence_ids, evidenceId]
  }
  if (!checked) {
    form.cited_evidence_ids = form.cited_evidence_ids.filter((id) => id !== evidenceId)
    form.step_evidence_links = form.step_evidence_links.filter(
      (link) => link.evidence_id !== evidenceId,
    )
  }
}

function linked(stepId: string, evidenceId: string): boolean {
  return form.step_evidence_links.some(
    (link) => link.step_id === stepId && link.evidence_id === evidenceId,
  )
}

function toggleLink(stepId: string, evidenceId: string, checked: boolean) {
  const others = form.step_evidence_links.filter(
    (link) => !(link.step_id === stepId && link.evidence_id === evidenceId),
  )
  form.step_evidence_links = checked
    ? [...others, { step_id: stepId, evidence_id: evidenceId }]
    : others
}

function saveDraft() {
  return game.saveDraft(content())
}

function submit() {
  if (!confirmed.value) return
  return game.submit(content())
}
</script>

<template>
  <ElCard header="正式指控">
    <div data-testid="accusation-form">
      <ElAlert
        v-if="game.error"
        type="error"
        :title="game.error"
        :closable="false"
        show-icon
        class="form-error"
      />
      <fieldset class="group">
        <legend>凶手</legend>
        <label
          v-for="o in options.suspects"
          :key="o.id"
          class="choice"
          :data-testid="`option-${o.id}`"
        >
          <input
            type="radio"
            name="suspect"
            :checked="form.suspect_character_id === o.id"
            @change="form.suspect_character_id = o.id"
          />
          {{ o.label }}
        </label>
      </fieldset>
      <fieldset class="group">
        <legend>凶器</legend>
        <label
          v-for="o in options.weapons"
          :key="o.id"
          class="choice"
          :data-testid="`option-${o.id}`"
        >
          <input
            type="radio"
            name="weapon"
            :checked="form.weapon_option_id === o.id"
            @change="form.weapon_option_id = o.id"
          />
          {{ o.label }}
        </label>
      </fieldset>
      <fieldset class="group">
        <legend>动机</legend>
        <label
          v-for="o in options.motives"
          :key="o.id"
          class="choice"
          :data-testid="`option-${o.id}`"
        >
          <input
            type="radio"
            name="motive"
            :checked="form.motive_option_id === o.id"
            @change="form.motive_option_id = o.id"
          />
          {{ o.label }}
        </label>
      </fieldset>
      <fieldset class="group">
        <legend>作案过程（按勾选的先后发生）</legend>
        <label
          v-for="o in options.process_steps"
          :key="o.id"
          class="choice"
          :data-testid="`step-${o.id}`"
        >
          <input
            type="checkbox"
            :checked="stepChecked(o.id)"
            @change="toggleStep(o.id, ($event.target as HTMLInputElement).checked)"
          />
          {{ o.label }}
        </label>
        <ol class="steps">
          <li v-for="(step, index) in form.ordered_process_step_ids" :key="step">
            第 {{ index + 1 }} 步：{{ label(step) }}
          </li>
        </ol>
      </fieldset>
      <fieldset class="group">
        <legend>引用证据（已持有）</legend>
        <label
          v-for="item in game.view?.evidence"
          :key="item.evidence_id"
          class="choice"
          :data-testid="`cite-check-${item.evidence_id}`"
        >
          <input
            type="checkbox"
            :checked="form.cited_evidence_ids.includes(item.evidence_id)"
            @change="toggleCited(item.evidence_id, ($event.target as HTMLInputElement).checked)"
          />
          {{ item.evidence_id }} · {{ item.name }}
        </label>
      </fieldset>
      <fieldset v-for="step in form.ordered_process_step_ids" :key="`links-${step}`" class="group">
        <legend>「{{ label(step) }}」的依据</legend>
        <label
          v-for="id in form.cited_evidence_ids"
          :key="`${step}-${id}`"
          class="choice"
          :data-testid="`link-${step}-${id}`"
        >
          <input
            type="checkbox"
            :checked="linked(step, id)"
            @change="toggleLink(step, id, ($event.target as HTMLInputElement).checked)"
          />
          {{ id }}
        </label>
      </fieldset>
      <ElInput
        v-model="form.explanation"
        data-testid="accusation-explanation"
        type="textarea"
        maxlength="4000"
        placeholder="补充说明（可选）"
      />
      <div class="actions">
        <ElButton :disabled="game.busy" data-testid="save-draft" @click="saveDraft">
          保存草稿
        </ElButton>
        <ElButton
          :disabled="game.busy"
          @click="game.cancelAccusation()"
          data-testid="cancel-accusation"
        >
          返回调查
        </ElButton>
      </div>
      <label data-testid="confirm-accusation" class="confirm">
        <input v-model="confirmed" type="checkbox" />
        我确认以当前填写内容正式结案，提交后不能再修改。
      </label>
      <div class="actions">
        <ElButton
          type="danger"
          data-testid="submit-accusation"
          :disabled="!confirmed || game.busy"
          @click="submit"
        >
          提交指控
        </ElButton>
      </div>
    </div>
  </ElCard>
</template>

<style scoped>
.form-error {
  margin-bottom: 12px;
}
.group {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px 12px;
  margin: 0 0 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
}
.choice {
  display: inline-flex;
  gap: 6px;
  align-items: center;
  font-weight: normal;
}
.steps {
  margin: 8px 0 0;
  padding-left: 20px;
  width: 100%;
}
.actions {
  display: flex;
  gap: 8px;
  margin: 8px 0;
}
.confirm {
  display: flex;
  gap: 8px;
  align-items: center;
  font-weight: normal;
  margin: 8px 0;
}
</style>
