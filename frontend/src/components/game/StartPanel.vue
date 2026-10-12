<script setup lang="ts">
import { ElButton, ElCard, ElEmpty } from 'element-plus'
import { useGameStore } from '../../stores/game'

const game = useGameStore()
</script>

<template>
  <ElCard header="选择案件">
    <ElEmpty v-if="!game.cases.length" description="尚无已发布案件，请先在后端导入案件。" />
    <div v-for="item in game.cases" :key="`${item.case_id}-${item.case_version}`" class="case">
      <h2>{{ item.title }}</h2>
      <p>{{ item.synopsis }}</p>
      <ElButton type="primary" :loading="game.busy" @click="game.start(item)">开始游戏</ElButton>
    </div>
  </ElCard>
</template>
