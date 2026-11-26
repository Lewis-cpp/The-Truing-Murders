import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { useGameStore } from './game'

export type DossierTab = 'evidence' | 'suspects' | 'board'
export type StageMode = 'lobby' | 'scene' | 'interrogation' | 'accusation' | 'review'

/** Presentation state only: which room is on stage and which dossier tab is open.
 *  Server state stays in the game store; this store only reads it. */
export const useStageStore = defineStore('stage', () => {
  const game = useGameStore()
  const chosenSceneId = ref<string | null>(null)
  const dossier = ref<DossierTab | null>(null)

  const mode = computed<StageMode>(() => {
    const view = game.view
    if (!view) return 'lobby'
    if (game.review) return 'review'
    if (view.session.phase === 'ACCUSATION') return 'accusation'
    if (view.session.active_npc_id) return 'interrogation'
    return 'scene'
  })

  // A choice the current game does not offer (a restart, a stale pick) falls back to
  // the first open room.
  const sceneId = computed(() => {
    const scenes = game.view?.scenes ?? []
    return scenes.some((scene) => scene.scene_id === chosenSceneId.value)
      ? chosenSceneId.value
      : (scenes[0]?.scene_id ?? null)
  })

  function showScene(id: string) {
    chosenSceneId.value = id
  }

  function toggleDossier(tab: DossierTab) {
    dossier.value = dossier.value === tab ? null : tab
  }

  return { mode, sceneId, dossier, showScene, toggleDossier }
})
