<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import {
  ElAlert,
  ElButton,
  ElCard,
  ElCheckbox,
  ElCheckboxGroup,
  ElForm,
  ElFormItem,
  ElInput,
  ElOption,
  ElSelect,
} from 'element-plus'
import { useGameStore } from '../../stores/game'
import type { AccusationContent } from '../../api/types'

const game = useGameStore()
const options = computed(() => game.view!.accusation_options)
// The draft comes from the server view; editing works on a local copy until it is saved.
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

function content(): AccusationContent {
  return JSON.parse(JSON.stringify(form))
}

function linksOf(step: string): string[] {
  return form.step_evidence_links
    .filter((link) => link.step_id === step)
    .map((link) => link.evidence_id)
}

function setLinks(step: string, ids: string[]) {
  const others = form.step_evidence_links.filter((link) => link.step_id !== step)
  form.step_evidence_links = [
    ...others,
    ...ids.map((evidence_id) => ({ step_id: step, evidence_id })),
  ]
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
      <ElForm label-width="96px">
        <ElFormItem label="凶手">
          <ElSelect v-model="form.suspect_character_id" placeholder="选择凶手">
            <ElOption v-for="o in options.suspects" :key="o.id" :label="o.label" :value="o.id" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="凶器">
          <ElSelect v-model="form.weapon_option_id" placeholder="选择凶器">
            <ElOption v-for="o in options.weapons" :key="o.id" :label="o.label" :value="o.id" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="动机">
          <ElSelect v-model="form.motive_option_id" placeholder="选择动机">
            <ElOption v-for="o in options.motives" :key="o.id" :label="o.label" :value="o.id" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="作案过程">
          <ElSelect
            v-model="form.ordered_process_step_ids"
            multiple
            placeholder="按发生顺序依次选择"
            style="width: 100%"
          >
            <ElOption
              v-for="o in options.process_steps"
              :key="o.id"
              :label="o.label"
              :value="o.id"
            />
          </ElSelect>
          <ol class="steps">
            <li v-for="step in form.ordered_process_step_ids" :key="step">{{ label(step) }}</li>
          </ol>
        </ElFormItem>
        <ElFormItem label="引用证据">
          <ElCheckboxGroup v-model="form.cited_evidence_ids">
            <ElCheckbox
              v-for="item in game.view?.evidence"
              :key="item.evidence_id"
              :value="item.evidence_id"
            >
              {{ item.evidence_id }} · {{ item.name }}
            </ElCheckbox>
          </ElCheckboxGroup>
        </ElFormItem>
        <ElFormItem
          v-for="(step, index) in form.ordered_process_step_ids"
          :key="`link-${step}`"
          :label="`第 ${index + 1} 步依据`"
        >
          <ElSelect
            :model-value="linksOf(step)"
            multiple
            placeholder="关联本次引用的证据"
            style="width: 100%"
            @update:model-value="(ids: string[]) => setLinks(step, ids)"
          >
            <ElOption v-for="id in form.cited_evidence_ids" :key="id" :label="id" :value="id" />
          </ElSelect>
        </ElFormItem>
        <ElFormItem label="补充说明">
          <ElInput v-model="form.explanation" type="textarea" maxlength="4000" />
        </ElFormItem>
        <ElFormItem>
          <ElButton :disabled="game.busy" data-testid="save-draft" @click="saveDraft">
            保存草稿
          </ElButton>
          <ElButton :disabled="game.busy" @click="game.cancelAccusation()">返回调查</ElButton>
        </ElFormItem>
        <ElFormItem>
          <label data-testid="confirm-accusation" class="confirm">
            <input v-model="confirmed" type="checkbox" />
            我确认以当前填写内容正式结案，提交后不能再修改。
          </label>
        </ElFormItem>
        <ElFormItem>
          <ElButton
            type="danger"
            data-testid="submit-accusation"
            :disabled="!confirmed || game.busy"
            @click="submit"
          >
            提交指控
          </ElButton>
        </ElFormItem>
      </ElForm>
    </div>
  </ElCard>
</template>

<style scoped>
.form-error {
  margin-bottom: 12px;
}
.steps {
  margin: 8px 0 0;
  padding-left: 20px;
}
.confirm {
  display: flex;
  gap: 8px;
  align-items: center;
  font-weight: normal;
}
</style>
