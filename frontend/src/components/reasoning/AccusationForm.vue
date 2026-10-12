<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import {
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

const game = useGameStore()
const options = computed(() => game.view!.accusation_options)
const form = reactive({
  suspect: '',
  weapon: '',
  motive: '',
  steps: [] as string[],
  cited: [] as string[],
  links: {} as Record<string, string[]>,
  explanation: '',
})
const confirmed = ref(false)
const label = (id: string) => options.value.process_steps.find((s) => s.id === id)?.label ?? id
const complete = computed(
  () => form.suspect && form.weapon && form.motive && form.steps.length && confirmed.value,
)

function submit() {
  game.submit({
    suspect_character_id: form.suspect,
    weapon_option_id: form.weapon,
    motive_option_id: form.motive,
    ordered_process_step_ids: [...form.steps],
    cited_evidence_ids: [...form.cited],
    step_evidence_links: form.steps.flatMap((step) =>
      (form.links[step] ?? [])
        .filter((id) => form.cited.includes(id))
        .map((evidenceId) => ({ step_id: step, evidence_id: evidenceId })),
    ),
    explanation: form.explanation,
  })
}
</script>

<template>
  <ElCard header="正式指控">
    <ElForm label-width="96px">
      <ElFormItem label="凶手">
        <ElSelect v-model="form.suspect" placeholder="选择凶手">
          <ElOption v-for="o in options.suspects" :key="o.id" :label="o.label" :value="o.id" />
        </ElSelect>
      </ElFormItem>
      <ElFormItem label="凶器">
        <ElSelect v-model="form.weapon" placeholder="选择凶器">
          <ElOption v-for="o in options.weapons" :key="o.id" :label="o.label" :value="o.id" />
        </ElSelect>
      </ElFormItem>
      <ElFormItem label="动机">
        <ElSelect v-model="form.motive" placeholder="选择动机">
          <ElOption v-for="o in options.motives" :key="o.id" :label="o.label" :value="o.id" />
        </ElSelect>
      </ElFormItem>
      <ElFormItem label="作案过程">
        <ElSelect
          v-model="form.steps"
          multiple
          placeholder="按发生顺序依次选择"
          style="width: 100%"
        >
          <ElOption v-for="o in options.process_steps" :key="o.id" :label="o.label" :value="o.id" />
        </ElSelect>
        <ol class="steps">
          <li v-for="step in form.steps" :key="step">{{ label(step) }}</li>
        </ol>
      </ElFormItem>
      <ElFormItem label="引用证据">
        <ElCheckboxGroup v-model="form.cited">
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
        v-for="(step, index) in form.steps"
        :key="`link-${step}`"
        :label="`第 ${index + 1} 步依据`"
      >
        <ElSelect
          v-model="form.links[step]"
          multiple
          placeholder="关联本次引用的证据"
          style="width: 100%"
        >
          <ElOption v-for="id in form.cited" :key="id" :label="id" :value="id" />
        </ElSelect>
      </ElFormItem>
      <ElFormItem label="补充说明">
        <ElInput v-model="form.explanation" type="textarea" maxlength="4000" />
      </ElFormItem>
      <ElFormItem>
        <ElCheckbox v-model="confirmed">我确认提交后本局结案，不能再修改。</ElCheckbox>
      </ElFormItem>
      <ElFormItem>
        <ElButton type="danger" :disabled="!complete || game.busy" @click="submit">
          提交指控
        </ElButton>
        <ElButton :disabled="game.busy" @click="game.cancelAccusation()">返回调查</ElButton>
      </ElFormItem>
    </ElForm>
  </ElCard>
</template>
