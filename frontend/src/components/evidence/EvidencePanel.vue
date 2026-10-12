<script setup lang="ts">
import { ElCard, ElEmpty, ElTag } from 'element-plus'
import { useGameStore } from '../../stores/game'

const game = useGameStore()
</script>

<template>
  <ElCard header="证据与证词">
    <ElEmpty v-if="!game.view?.evidence.length" description="尚未取得证据。" :image-size="60" />
    <article v-for="item in game.view?.evidence" :key="item.evidence_id" class="evidence">
      <h3>
        {{ item.evidence_id }} · {{ item.name }}
        <ElTag size="small" :type="item.credibility === 'VERIFIED' ? 'success' : 'warning'">
          {{ item.credibility === 'VERIFIED' ? '已核验' : '未核验' }}
        </ElTag>
      </h3>
      <p>{{ item.content }}</p>
      <p class="source">来源：{{ item.source.label }}</p>
    </article>
    <article
      v-for="info in game.view?.known_information"
      :key="info.information_ref.id"
      class="evidence"
    >
      <h3>
        证词 · {{ info.source.label }}
        <ElTag size="small" type="warning">未经核验</ElTag>
      </h3>
      <p>{{ info.content }}</p>
    </article>
  </ElCard>
</template>
