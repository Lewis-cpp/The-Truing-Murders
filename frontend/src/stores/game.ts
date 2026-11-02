import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  ApiError,
  ensureVisitor,
  get,
  newWrite,
  send,
  UncertainError,
  type PendingWrite,
} from '../api/client'
import type {
  AccusationContent,
  ActionResult,
  CaseSummary,
  ConversationPage,
  ConversationView,
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
// Rejections meaning the page shows an outdated save, e.g. another tab saved or restarted.
const OUTDATED = [
  'STATE_VERSION_CONFLICT',
  'SAVE_VERSION_UNSUPPORTED',
  'SESSION_NOT_CURRENT',
  'CURRENT_SESSION_CONFLICT',
  'CURRENT_SESSION_EXISTS',
]
// Rounds waiting for the model; the page polls each one until it settles.
const PENDING_ROUNDS = ['PREPARING', 'GENERATING']
const POLL_INTERVAL_MS = 1500
// Polls kept after the deadline: a late model call settles shortly after it, a lost task never.
const EXPIRED_POLL_LIMIT = 4

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
  // A confirmed write whose follow-up read failed; the page needs a reload.
  const stale = ref(false)
  const pending = ref<PendingWrite | null>(null)
  const conversations = ref<ConversationView[]>([])
  // Evidence ids the reasoning board asks the accusation form to cite; the form drains
  // the queue because the form state itself stays local to that component.
  const citeRequests = ref<string[]>([])
  // The round the page is polling for, if any; the timer itself stays non-reactive.
  const pollingId = ref<string | null>(null)
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let expiredPolls = 0

  function base(): string {
    return `/api/v1/sessions/${view.value?.session.session_id}`
  }

  function version(): number | undefined {
    return view.value?.session.state_version
  }

  function stopPolling() {
    if (pollTimer !== null) {
      clearInterval(pollTimer)
      pollTimer = null
    }
    pollingId.value = null
  }

  async function pollOnce() {
    const conversationId = pollingId.value
    if (!conversationId || !view.value) {
      stopPolling()
      return
    }
    try {
      const body = await get<{ data: ConversationView }>(
        `${base()}/conversations/${conversationId}`,
      )
      const round = body.data
      // A reply for a round or person the page has since left is dropped, not shown here.
      if (pollingId.value !== conversationId || round.npc_id !== view.value?.session.active_npc_id)
        return
      const index = conversations.value.findIndex((item) => item.conversation_id === conversationId)
      if (index >= 0) conversations.value.splice(index, 1, round)
      else conversations.value.push(round)
      // A final state ends the polling; the server writes it, the page only reads it.
      if (!PENDING_ROUNDS.includes(round.generation_status)) stopPolling()
      else if (round.deadline_exceeded && ++expiredPolls >= EXPIRED_POLL_LIMIT) stopPolling()
    } catch {
      // A failed poll keeps the placeholder; the next tick tries again.
    }
  }

  function startPolling(conversationId: string) {
    if (pollTimer !== null && pollingId.value === conversationId) return
    stopPolling()
    expiredPolls = 0
    pollingId.value = conversationId
    pollTimer = setInterval(() => {
      void pollOnce()
    }, POLL_INTERVAL_MS)
  }

  async function loadConversations() {
    const npcId = view.value?.session.active_npc_id
    if (view.value?.session.phase !== 'INTERROGATION' || !npcId) {
      conversations.value = []
      return
    }
    const page = await get<{ data: ConversationPage }>(
      `${base()}/npcs/${npcId}/conversations?limit=20`,
    )
    // The API returns the newest first; the transcript reads in conversation order.
    conversations.value = [...page.data.items].sort(
      (left, right) => left.conversation_seq - right.conversation_seq,
    )
    const waiting = conversations.value.find(
      (round) => PENDING_ROUNDS.includes(round.generation_status) && !round.deadline_exceeded,
    )
    if (waiting) startPolling(waiting.conversation_id)
    // A round of another person (the page switched) stops; a just-retried one keeps polling.
    else if (!conversations.value.some((round) => round.conversation_id === pollingId.value))
      stopPolling()
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
      conversations.value = []
      stopPolling()
      unsupported.value = caught.details as unknown as UnsupportedSave
      review.value = null
      return
    }
    review.value = null
    const phase = view.value?.session.phase
    // Leaving an interrogation by any route (back, accusation, restart) ends its transcript
    // and stops the polling with it.
    if (phase !== 'INTERROGATION') {
      conversations.value = []
      stopPolling()
    }
    if (phase === 'REVIEW' || phase === 'FINISHED') {
      review.value = (await get<{ data: ReviewView }>(`${base()}/review`)).data
    }
    await loadConversations()
  }

  async function init() {
    loading.value = true
    error.value = null
    stale.value = false
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
    // Browser fetch errors carry English text such as "Failed to fetch".
    if (caught instanceof ApiError || caught instanceof UncertainError) return caught.message
    return '网络异常，请稍后重试。'
  }

  async function run(
    write: PendingWrite,
    onSuccess?: (data: DataWithSummary, result: ActionResult<DataWithSummary>) => void,
  ) {
    busy.value = true
    error.value = null
    notice.value = null
    stale.value = false
    pending.value = write
    try {
      const result = await send<DataWithSummary>(write)
      pending.value = null
      onSuccess?.(result.data, result)
      try {
        await refresh()
      } catch {
        // The write is saved; only the page is behind, so offer a reload, not a resend.
        stale.value = true
        error.value = '操作已保存，但读取最新进度失败，请重新加载。'
      }
    } catch (caught) {
      // Keep the same key only when the outcome is unknown; a definite rejection needs a new
      // operation against the latest state.
      const uncertain = !(caught instanceof ApiError) || caught.retryable
      if (!uncertain) pending.value = null
      error.value = describe(caught)
      const code = caught instanceof ApiError ? caught.code : null
      if (code && OUTDATED.includes(code)) await refresh().catch(() => undefined)
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
  }

  function emptyDraft(): AccusationContent {
    return {
      suspect_character_id: null,
      weapon_option_id: null,
      motive_option_id: null,
      ordered_process_step_ids: [],
      cited_evidence_ids: [],
      step_evidence_links: [],
      explanation: '',
    }
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
    stale,
    pending,
    conversations,
    citeRequests,
    pollingId,
    stopPolling,
    // Read-only: polls an expired round again, for a settlement after the page stopped waiting.
    checkRound: startPolling,
    emptyDraft,
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
    retryReply: (conversationId: string) =>
      run(
        newWrite('POST', `${base()}/conversations/${conversationId}/reply-retries`, {}, version()),
        // The accepted retry answers with the round back in PREPARING; poll it again.
        (_data, result) => {
          const round = result.conversation
          if (round && PENDING_ROUNDS.includes(round.generation_status)) {
            startPolling(round.conversation_id)
          }
        },
      ),
    askTopic: (npcId: string, topicId: string) =>
      run(
        newWrite('POST', `${base()}/npcs/${npcId}/questions`, { topic_id: topicId }, version()),
        summarize,
      ),
    present: (npcId: string, evidenceId: string, comment?: string) =>
      run(
        newWrite(
          'POST',
          `${base()}/npcs/${npcId}/evidence-presentations`,
          { evidence_id: evidenceId, ...(comment ? { comment } : {}) },
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
    saveDraft: (content: AccusationContent) =>
      run(newWrite('PUT', `${base()}/accusation-draft`, { content }, version()), summarize),
    openAccusation: () => run(newWrite('PUT', `${base()}/accusation-preparation`, {}, version())),
    cancelAccusation: () =>
      run(newWrite('DELETE', `${base()}/accusation-preparation`, undefined, version())),
    submit: (content: AccusationContent) =>
      run(newWrite('POST', `${base()}/accusation`, { content, confirm: true }, version())),
    finish: () => run(newWrite('PUT', `${base()}/review-completion`, {}, version())),
    citeEvidence: (evidenceId: string) => {
      citeRequests.value.push(evidenceId)
    },
  }
})
