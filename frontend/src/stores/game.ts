import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ApiError, ensureVisitor, get, newWrite, send, type PendingWrite } from '../api/client'
import type {
  AccusationContent,
  CaseSummary,
  CurrentSessionView,
  ReviewView,
  SessionView,
} from '../api/types'

interface Notice {
  kind: 'success' | 'info'
  text: string
}

interface DataWithSummary {
  outcome?: { summary: string }
  fixed_reply?: string
}

/** Server state only. The page is always rebuilt from a fresh GET after a confirmed write. */
export const useGameStore = defineStore('game', () => {
  const loading = ref(true)
  const busy = ref(false)
  const cases = ref<CaseSummary[]>([])
  const view = ref<SessionView | null>(null)
  const review = ref<ReviewView | null>(null)
  const notice = ref<Notice | null>(null)
  const error = ref<string | null>(null)
  const pending = ref<PendingWrite | null>(null)
  const replies = ref<string[]>([])

  function base(): string {
    return `/api/v1/sessions/${view.value?.session.session_id}`
  }

  function version(): number | undefined {
    return view.value?.session.state_version
  }

  async function refresh() {
    const current = await get<CurrentSessionView>('/api/v1/sessions/current')
    view.value = current.session
    review.value = null
    const phase = current.session?.session.phase
    if (phase === 'REVIEW' || phase === 'FINISHED') {
      review.value = (await get<{ data: ReviewView }>(`${base()}/review`)).data
    }
  }

  async function init() {
    loading.value = true
    error.value = null
    try {
      await ensureVisitor()
      cases.value = (await get<{ items: CaseSummary[] }>('/api/v1/cases')).items
      await refresh()
    } catch (caught) {
      error.value = describe(caught)
    } finally {
      loading.value = false
    }
  }

  function describe(caught: unknown): string {
    if (caught instanceof Error) return caught.message
    return '操作失败，请重试。'
  }

  async function run(write: PendingWrite, onSuccess?: (data: DataWithSummary) => void) {
    busy.value = true
    error.value = null
    notice.value = null
    pending.value = write
    try {
      const result = await send<DataWithSummary>(write)
      pending.value = null
      onSuccess?.(result.data)
      await refresh()
    } catch (caught) {
      // Keep the same key only when the outcome is unknown; a definite rejection needs a new
      // operation against the latest state.
      const uncertain = !(caught instanceof ApiError) || caught.retryable
      if (!uncertain) pending.value = null
      error.value = describe(caught)
      if (caught instanceof ApiError && caught.code === 'STATE_VERSION_CONFLICT') {
        await refresh().catch(() => undefined)
      }
    } finally {
      busy.value = false
    }
  }

  function summarize(data: DataWithSummary) {
    if (data.outcome) notice.value = { kind: 'success', text: data.outcome.summary }
    if (data.fixed_reply) replies.value = [...replies.value, data.fixed_reply]
  }

  return {
    loading,
    busy,
    cases,
    view,
    review,
    notice,
    error,
    pending,
    replies,
    init,
    retry: () => pending.value && run(pending.value, summarize),
    start: (game: CaseSummary) =>
      run(
        newWrite('POST', '/api/v1/sessions', {
          case_id: game.case_id,
          case_version: game.case_version,
        }),
      ),
    restart: (game: CaseSummary) =>
      run(
        newWrite(
          'POST',
          '/api/v1/sessions',
          {
            case_id: game.case_id,
            case_version: game.case_version,
            replaces_session_id: view.value?.session.session_id,
            confirm_restart: true,
          },
          version(),
        ),
        () => {
          replies.value = []
        },
      ),
    investigate: (sceneId: string, actionId: string) =>
      run(
        newWrite(
          'POST',
          `${base()}/scenes/${sceneId}/investigations`,
          { action_id: actionId },
          version(),
        ),
        summarize,
      ),
    talk: (npcId: string) =>
      run(newWrite('PUT', `${base()}/interrogation`, { npc_id: npcId }, version())),
    endTalk: () => run(newWrite('DELETE', `${base()}/interrogation`, undefined, version())),
    chat: (npcId: string, message: string) =>
      run(
        newWrite('POST', `${base()}/npcs/${npcId}/conversations`, { message }, version()),
        summarize,
      ),
    present: (npcId: string, evidenceId: string) =>
      run(
        newWrite(
          'POST',
          `${base()}/npcs/${npcId}/evidence-presentations`,
          { evidence_id: evidenceId },
          version(),
        ),
        summarize,
      ),
    openAccusation: () => run(newWrite('PUT', `${base()}/accusation-preparation`, {}, version())),
    cancelAccusation: () =>
      run(newWrite('DELETE', `${base()}/accusation-preparation`, undefined, version())),
    submit: (content: AccusationContent) =>
      run(newWrite('POST', `${base()}/accusation`, { content, confirm: true }, version())),
    finish: () => run(newWrite('PUT', `${base()}/review-completion`, {}, version())),
  }
})
