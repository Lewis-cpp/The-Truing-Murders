<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElButton } from 'element-plus'

const status = ref<'checking' | 'ready' | 'error'>('checking')

async function checkConnection() {
  status.value = 'checking'
  try {
    const response = await fetch('/api/v1/ready', { signal: AbortSignal.timeout(5000) })
    if (!response.ok) throw new Error('Service unavailable')
    const result = await response.json()
    status.value = result.status === 'ok' && result.database === 'ok' ? 'ready' : 'error'
  } catch {
    status.value = 'error'
  }
}

onMounted(checkConnection)
</script>

<template>
  <main>
    <p class="eyebrow">THE TRUING MURDERS</p>
    <h1>开发环境</h1>
    <p>这是项目启动检查页。游戏功能将按开发计划逐步实现。</p>
    <p role="status" aria-live="polite" :class="status">
      <template v-if="status === 'checking'">正在检查服务连接……</template>
      <template v-else-if="status === 'ready'">前端、后端与数据库已连通。</template>
      <template v-else>连接失败，请检查后端与数据库是否已启动。</template>
    </p>
    <ElButton :loading="status === 'checking'" @click="checkConnection">重新检查</ElButton>
  </main>
</template>
