// v0.4 acceptance: the page polls a pending round, stops at a final state and offers retries.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import GameView from '../src/views/GameView.vue'
import { useGameStore } from '../src/stores/game'
import type { SessionView } from '../src/api/types'
import { json, stubFetch } from './fixtures'

const id = '00000000-0000-4000-8000-000000000004'
const session = `/api/v1/sessions/${id}`
const conversationId = '00000000-0000-4000-8000-000000000444'

beforeEach(() => {
  setActivePinia(createPinia())
  vi.useFakeTimers()
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

function round(status: string, extra: Record<string, unknown> = {}) {
  const npcMessage = {
    message_id: 'n1',
    sequence_no: 2,
    speaker: 'NPC',
    content: status === 'COMPLETED' ? '我需要核对一下。' : '停电时我一直在休息区。',
    origin: status === 'COMPLETED' ? 'LLM' : 'FIXED',
    validity: 'VALID',
    created_at: '2026-11-01T00:00:00Z',
    updated_at: '2026-11-01T00:00:00Z',
  }
  return {
    conversation_id: conversationId,
    conversation_seq: 1,
    session_id: id,
    npc_id: 'NPC01',
    request_id: '00000000-0000-4000-8000-000000000555',
    interaction_type: 'CHAT',
    source_state_version: 9,
    generation_status: status,
    generation_deadline_at: '2026-11-01T00:00:30Z',
    deadline_exceeded: false,
    fixed_reply: '停电时我一直在休息区。',
    messages: [
      {
        message_id: 'p1',
        sequence_no: 1,
        speaker: 'PLAYER',
        content: '你在哪里？',
        origin: 'PLAYER',
        validity: 'VALID',
        created_at: '2026-11-01T00:00:00Z',
        updated_at: '2026-11-01T00:00:00Z',
      },
      ...(['PREPARING', 'GENERATING'].includes(status) ? [] : [npcMessage]),
    ],
    fallback_reason: null,
    can_retry_reply: false,
    created_at: '2026-11-01T00:00:00Z',
    completed_at: null,
    ...extra,
  }
}

function talkingView(pending: unknown[] = []): SessionView {
  return {
    session: {
      session_id: id,
      case_id: 'case_001',
      case_version: '3-full',
      title: '停电之夜',
      phase: 'INTERROGATION',
      state_version: 9,
      active_npc_id: 'NPC01',
      is_current: true,
      created_at: '2026-11-01T00:00:00Z',
      saved_at: '2026-11-01T00:00:00Z',
      closed_at: null,
      finished_at: null,
      available_actions: [
        'SET_INTERROGATION',
        'END_INTERROGATION',
        'CHAT',
        'PRESENT_EVIDENCE',
        'OPEN_ACCUSATION',
        'RESTART',
      ],
    },
    intro_text: '案发当晚。',
    scenes: [],
    evidence: [],
    npcs: [
      {
        npc_id: 'NPC01',
        name: '沈砚',
        public_identity: '副研究员',
        is_contactable: true,
        is_active: true,
        is_evading: false,
        emotion: 'CALM',
        admission_progress: 'NONE',
        display_state: 'CALM',
        fixed_statement: '停电时我一直在休息区。',
        presented_evidence_ids: [],
        known_statements: [],
        topics: [],
      },
    ],
    known_information: [],
    relationships: { nodes: [], edges: [] },
    timeline: { origin_label: '案发当日 00:00', items: [] },
    accusation_options: {
      suspects: [],
      weapons: [],
      motives: [],
      process_steps: [],
      process_constraints: {
        min_steps: 1,
        max_steps: 5,
        allow_repeated_steps: false,
      },
    },
    accusation_draft: {
      suspect_character_id: null,
      weapon_option_id: null,
      motive_option_id: null,
      ordered_process_step_ids: [],
      cited_evidence_ids: [],
      step_evidence_links: [],
      explanation: '',
    },
    pending_conversations: pending,
  } as unknown as SessionView
}

const base = {
  'POST /api/v1/visitors': () => json(200, { current_session_id: id }),
  'GET /api/v1/cases': () => json(200, { items: [] }),
}

async function mountView() {
  const wrapper = mount(GameView, {
    global: { plugins: [createPinia()] },
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

describe('generation polling', () => {
  it('shows a placeholder, polls the round and stops once it completes', async () => {
    const states = [
      round('GENERATING'),
      round('COMPLETED', { completed_at: '2026-11-01T00:00:03Z' }),
    ]
    let polls = 0
    stubFetch({
      ...base,
      'GET /api/v1/sessions/current': () =>
        json(200, {
          current_session_id: id,
          session: talkingView([round('PREPARING')]),
        }),
      [`GET ${session}/npcs/NPC01/conversations?limit=20`]: () =>
        json(200, {
          session_id: id,
          state_version: 9,
          data: { items: [round('PREPARING')], next_before_seq: null },
        }),
      [`GET ${session}/conversations/${conversationId}`]: () => {
        polls += 1
        const current = states.length > 1 ? states.shift()! : states[0]
        return json(200, { session_id: id, state_version: 9, data: current })
      },
    })
    const wrapper = await mountView()
    expect(wrapper.get('[data-testid="conversation-log"]').text()).toContain('回复准备中')
    await vi.advanceTimersByTimeAsync(1600)
    expect(polls).toBe(1)
    await vi.advanceTimersByTimeAsync(1600)
    expect(polls).toBe(2)
    expect(wrapper.get('[data-testid="conversation-log"]').text()).toContain('我需要核对一下。')
    await vi.advanceTimersByTimeAsync(6000)
    expect(polls).toBe(2)
    wrapper.unmount()
  })

  it('explains a fallback and retries with a new key only when allowed', async () => {
    const fallback = round('FALLBACK', {
      fallback_reason: 'MODEL_TIMEOUT',
      can_retry_reply: true,
      completed_at: '2026-11-01T00:00:31Z',
    })
    const bodies: unknown[] = []
    stubFetch({
      ...base,
      'GET /api/v1/sessions/current': () =>
        json(200, { current_session_id: id, session: talkingView() }),
      [`GET ${session}/npcs/NPC01/conversations?limit=20`]: () =>
        json(200, {
          session_id: id,
          state_version: 9,
          data: { items: [fallback], next_before_seq: null },
        }),
      [`POST ${session}/conversations/${conversationId}/reply-retries`]: (init) => {
        bodies.push(JSON.parse(init!.body as string))
        return json(201, {
          request_id: 'r',
          session_id: id,
          business_status: 'COMMITTED',
          state_changed: false,
          state_version_before: 9,
          result_state_version: 9,
          phase_after: 'INTERROGATION',
          active_npc_id_after: 'NPC01',
          saved_at: '2026-11-01T00:00:00Z',
          data: { conversation_id: conversationId },
          conversation: round('PREPARING'),
        })
      },
      [`GET ${session}/conversations/${conversationId}`]: () =>
        json(200, {
          session_id: id,
          state_version: 9,
          data: round('COMPLETED'),
        }),
    })
    const wrapper = await mountView()
    expect(wrapper.get('[data-testid="fallback-notice"]').text()).toContain('固定回复')
    expect(wrapper.text()).toContain('停电时我一直在休息区。')
    await wrapper.get('[data-testid="retry-reply"]').trigger('click')
    await flushPromises()
    expect(bodies).toEqual([{}])
    await vi.advanceTimersByTimeAsync(1600)
    expect(wrapper.get('[data-testid="conversation-log"]').text()).toContain('我需要核对一下。')
    expect(wrapper.find('[data-testid="retry-reply"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('offers no retry when the server says no', async () => {
    const rejected = round('FALLBACK', {
      fallback_reason: 'MODEL_OUTPUT_REJECTED',
      can_retry_reply: false,
    })
    stubFetch({
      ...base,
      'GET /api/v1/sessions/current': () =>
        json(200, { current_session_id: id, session: talkingView() }),
      [`GET ${session}/npcs/NPC01/conversations?limit=20`]: () =>
        json(200, {
          session_id: id,
          state_version: 9,
          data: { items: [rejected], next_before_seq: null },
        }),
    })
    const wrapper = await mountView()
    expect(wrapper.find('[data-testid="fallback-notice"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="retry-reply"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('stops waiting for an expired round and says the question can go on', async () => {
    let polls = 0
    stubFetch({
      ...base,
      'GET /api/v1/sessions/current': () =>
        json(200, { current_session_id: id, session: talkingView([round('PREPARING')]) }),
      [`GET ${session}/npcs/NPC01/conversations?limit=20`]: () =>
        json(200, {
          session_id: id,
          state_version: 9,
          data: { items: [round('PREPARING')], next_before_seq: null },
        }),
      [`GET ${session}/conversations/${conversationId}`]: () => {
        polls += 1
        return json(200, {
          session_id: id,
          state_version: 9,
          data: round('PREPARING', { deadline_exceeded: true }),
        })
      },
    })
    const wrapper = await mountView()
    await vi.advanceTimersByTimeAsync(6000)
    expect(polls).toBe(1)
    expect(wrapper.find('[data-testid="reply-expired"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it("drops the last person's pending reply after switching to another", async () => {
    let active = 'NPC01'
    let polls = 0
    const other = { ...talkingView().npcs[0], npc_id: 'NPC02', name: '林澄' }
    const viewOf = () => {
      const view = talkingView()
      view.session.active_npc_id = active
      view.npcs = [view.npcs[0], other] as typeof view.npcs
      return view
    }
    stubFetch({
      ...base,
      'GET /api/v1/sessions/current': () =>
        json(200, { current_session_id: id, session: viewOf() }),
      [`GET ${session}/npcs/NPC01/conversations?limit=20`]: () =>
        json(200, {
          session_id: id,
          state_version: 9,
          data: { items: [round('PREPARING')], next_before_seq: null },
        }),
      [`GET ${session}/npcs/NPC02/conversations?limit=20`]: () =>
        json(200, {
          session_id: id,
          state_version: 9,
          data: { items: [], next_before_seq: null },
        }),
      [`GET ${session}/conversations/${conversationId}`]: () => {
        polls += 1
        return json(200, { session_id: id, state_version: 9, data: round('COMPLETED') })
      },
    })
    const pinia = createPinia()
    const wrapper = mount(GameView, { global: { plugins: [pinia] }, attachTo: document.body })
    await flushPromises()
    const game = useGameStore(pinia)
    expect(game.pollingId).toBe(conversationId)
    active = 'NPC02'
    await game.init()
    await vi.advanceTimersByTimeAsync(6000)
    expect(game.pollingId).toBeNull()
    expect(polls).toBe(0)
    expect(game.conversations).toEqual([])
    wrapper.unmount()
  })
})
