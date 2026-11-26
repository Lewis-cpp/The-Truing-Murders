<script setup lang="ts">
import { computed } from 'vue'
import { backdropFor } from '../../assets/stageManifest'
import { useStageStore } from '../../stores/stage'

const stage = useStageStore()
const key = computed(() => {
  if (stage.mode === 'scene') return stage.sceneId ?? 'cover'
  if (stage.mode === 'interrogation' || stage.mode === 'accusation') return 'interrogation'
  return 'cover'
})
</script>

<template>
  <!-- Decoration only: the layers crossfade when the stage changes. -->
  <div class="backdrop" aria-hidden="true">
    <Transition name="backdrop-fade">
      <div :key="key" class="layer" :data-stage="key" :style="{ background: backdropFor(key) }" />
    </Transition>
  </div>
</template>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  z-index: -1;
  background: var(--tm-ink);
}
.layer {
  position: absolute;
  inset: 0;
}
.backdrop-fade-enter-active,
.backdrop-fade-leave-active {
  /* A room change reads as a slow light change; still zero under reduced motion. */
  transition: opacity calc(var(--tm-motion-duration) * 2.5);
}
.backdrop-fade-enter-from,
.backdrop-fade-leave-to {
  opacity: 0;
}
</style>
