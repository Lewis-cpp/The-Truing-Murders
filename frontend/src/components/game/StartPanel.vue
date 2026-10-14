<script setup lang="ts">
import { ElButton, ElCard, ElEmpty, ElPopconfirm } from 'element-plus'
import { useGameStore } from '../../stores/game'

const game = useGameStore()
</script>

<template>
  <ElCard header="选择案件">
    <ElEmpty v-if="!game.cases.length" description="尚无已发布案件，请先在后端导入案件。" />
    <div v-for="item in game.cases" :key="`${item.case_id}-${item.case_version}`" class="case">
      <h2>{{ item.title }}</h2>
      <p>{{ item.synopsis }}</p>
      <ElPopconfirm
        v-if="game.unsupported"
        title="新的一局会成为当前存档；无法读取的旧存档仍会保留。确定开始？"
        confirm-button-text="开始"
        cancel-button-text="取消"
        @confirm="game.start(item)"
      >
        <template #reference>
          <ElButton type="primary" :loading="game.busy">开始新的一局</ElButton>
        </template>
      </ElPopconfirm>
      <ElButton v-else type="primary" :loading="game.busy" @click="game.start(item)">
        开始游戏
      </ElButton>
    </div>
  </ElCard>
</template>
