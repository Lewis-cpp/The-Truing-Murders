import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ApiError, ensureVisitor, get, newWrite, send, type PendingWrite } from '../api/client'
import type {
  AccusationContent,
  CaseSummary,
  CurrentSessionView,
  PlayerOutcome,
  ReviewView,
  SessionView,
  UnsupportedSave,
} from '../api/types'

interface Notice {
  kind: 'success' | 'info' | 'warning'
  text: string
}

interface DataWithSummary {
  outcome?: PlayerOutcome
  fixed_reply?: string
}

// Outcomes where the NPC grew warier or would not engage; shown as a warning, not a success.
const SETBACKS = ['IRRELEVANT_MOVE', 'NPC_EVADING']

/** Server state only. The page is always rebuilt from a fresh GET after a confirmed write. */
export const useGameStore = defineStore('game', () => {
  const loading = ref(true)
  const busy = ref(false)
  const cases = ref<CaseSummary[]>([])
  const view = ref<SessionView | null>(null)
  const unsupported = ref<UnsupportedSave | null>(null)
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
    try {
      const current = await get<CurrentSessionView>('/api/v1/sessions/current')
      view.value = current.session
      unsupported.value = null
    } catch (caught) {
      // The server keeps the save; the lobby offers a new game that replaces it.
      if (!(caught instanceof ApiError) || caught.code !== 'SAVE_VERSION_UNSUPPORTED') throw caught
      view.value = null
      unsupported.value = caught.details as unknown as UnsupportedSave
    }
    review.value = null
    const phase = view.value?.session.phase
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
      const code = caught instanceof ApiError ? caught.code : null
      if (code === 'STATE_VERSION_CONFLICT' || code === 'SAVE_VERSION_UNSUPPORTED') {
        await refresh().catch(() => undefined)
      }
      // The lobby warning already explains an unreadable save.
      if (code === 'SAVE_VERSION_UNSUPPORTED' && unsupported.value) error.value = null
    } finally {
      busy.value = false
    }
  }

  function summarize(data: DataWithSummary) {
    if (data.outcome) {
      const kind = SETBACKS.includes(data.outcome.reason_code) ? 'warning' : 'success'
      notice.value = { kind, text: data.outcome.summary }
    }
    if (data.fixed_reply) replies.value = [...replies.value, data.fixed_reply]
  }

  return {
    loading,
    busy,
    cases,
    view,
    unsupported,
    review,
    notice,
    error,
    pending,
    replies,
    init,
    retry: () => pending.value && run(pending.value, summarize),
    start: (game: CaseSummary) => {
      const old = unsupported.value
      const body = { case_id: game.case_id, case_version: game.case_version }
      // An unreadable save stays stored; the new game only takes its place as the current one.
      const replacing = old ? { replaces_session_id: old.session_id, confirm_restart: true } : {}
      return run(
        newWrite('POST', '/api/v1/sessions', { ...body, ...replacing }, old?.state_version),
      )
    },
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
    endTalk: () =>
      run(newWrite('DELETE', `${base()}/interrogation`, undefined, version()), () => {
        // Evasion ends with the interrogation, so the next one starts a fresh transcript.
        replies.value = []
      }),
    chat: (npcId: string, message: string) =>
      run(
        newWrite('POST', `${base()}/npcs/${npcId}/conversations`, { message }, version()),
        summarize,
      ),
    askTopic: (npcId: string, topicId: string) =>
      run(
        newWrite('POST', `${base()}/npcs/${npcId}/questions`, { topic_id: topicId }, version()),
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
    contradict: (npcId: string, knowledgeId: string, evidenceId: string) =>
      run(
        newWrite(
          'POST',
          `${base()}/npcs/${npcId}/contradictions`,
          { knowledge_id: knowledgeId, evidence_id: evidenceId },
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
