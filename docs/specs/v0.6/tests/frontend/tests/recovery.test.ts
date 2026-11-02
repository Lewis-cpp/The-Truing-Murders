// v0.6 acceptance: uncertain writes are looked up, retried with the same key, and never lose input.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import GameView from '../src/views/GameView.vue'
import type { SessionView } from '../src/api/types'
import { json, stubFetch } from './fixtures'

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.unstubAllGlobals())

const id = '00000000-0000-4000-8000-000000000006'
const session = `/api/v1/sessions/${id}`
const emptyDraft = {
  suspect_character_id: null,
  weapon_option_id: null,
  motive_option_id: null,
  ordered_process_step_ids: [],
  cited_evidence_ids: [],
  step_evidence_links: [],
  explanation: '',
}

function view(phase: string, activeNpc: string | null): SessionView {
  return {
    session: {
      session_id: id,
      case_id: 'case_001',
      case_version: '3-full',
      title: '停电之夜',
      phase,
      state_version: 9,
      active_npc_id: activeNpc,
      is_current: true,
      created_at: '2026-11-01T00:00:00Z',
      saved_at: '2026-11-01T00:00:00Z',
      closed_at: null,
      finished_at: null,
      generation_available: true,
      available_actions:
        phase === 'ACCUSATION'
          ? ['SAVE_ACCUSATION_DRAFT', 'SUBMIT_ACCUSATION', 'CANCEL_ACCUSATION', 'RESTART']
          : [
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
        npc_id: 'NPC02',
        name: '许岚',
        public_identity: '档案管理员',
        is_contactable: true,
        is_active: activeNpc === 'NPC02',
        is_evading: false,
        emotion: 'CALM',
        admission_progress: 'NONE',
        display_state: 'CALM',
        fixed_statement: activeNpc ? '我没有把B17材料借给别人。' : null,
        presented_evidence_ids: [],
        known_statements: [],
        topics: [],
      },
    ],
    known_information: [],
    relationships: { nodes: [], edges: [] },
    timeline: { origin_label: '案发当日 00:00', items: [] },
    accusation_options: {
      suspects: [{ id: 'NPC02', label: '许岚 · 档案管理员' }],
      weapons: [{ id: 'W01', label: '铜镇纸' }],
      motives: [{ id: 'M01', label: '阻止实验造假被移交审计' }],
      process_steps: [{ id: 'P_ENTER', label: '停电期间进入档案室' }],
      process_constraints: {
        min_steps: 1,
        max_steps: 5,
        allow_repeated_steps: false,
      },
    },
    accusation_draft: emptyDraft,
    pending_conversations: [],
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

describe('recovery', () => {
  it('looks up a chat whose response was lost and retries it with the same key', async () => {
    const keys: string[] = []
    const bodies: string[] = []
    let lookups = 0
    stubFetch({
      ...base,
      'GET /api/v1/sessions/current': () =>
        json(200, {
          current_session_id: id,
          session: view('INTERROGATION', 'NPC02'),
        }),
      [`GET ${session}/npcs/NPC02/conversations?limit=20`]: () =>
        json(200, {
          session_id: id,
          state_version: 9,
          data: { items: [], next_before_seq: null },
        }),
      [`POST ${session}/npcs/NPC02/conversations`]: (init) => {
        keys.push((init!.headers as Record<string, string>)['Idempotency-Key'])
        bodies.push(init!.body as string)
        if (keys.length === 1) throw new TypeError('network down')
        return json(201, {
          request_id: keys[0],
          session_id: id,
          business_status: 'COMMITTED',
          state_changed: false,
          state_version_before: 9,
          result_state_version: 9,
          phase_after: 'INTERROGATION',
          active_npc_id_after: 'NPC02',
          saved_at: '2026-11-01T00:00:00Z',
          data: { conversation_id: '00000000-0000-4000-8000-000000000777' },
          conversation: null,
        })
      },
      'GET *': () => {
        lookups += 1
        return json(404, {
          error: {
            code: 'REQUEST_NOT_FOUND',
            message: '没有找到该操作。',
            details: {},
            retryable: false,
          },
        })
      },
    })
    const wrapper = await mountView()
    await wrapper
      .get(
        '[data-testid="chat-input"] textarea, [data-testid="chat-input"] input, textarea[data-testid="chat-input"], input[data-testid="chat-input"]',
      )
      .setValue('你好')
    await wrapper.get('[data-testid="chat-send"]').trigger('click')
    await flushPromises()
    expect(lookups).toBe(1)
    expect(wrapper.text()).toContain('未确认保存')
    const retry = wrapper.findAll('button').find((b) => b.text() === '重试同一操作')!
    await retry.trigger('click')
    await flushPromises()
    expect(keys).toHaveLength(2)
    expect(keys[1]).toBe(keys[0])
    expect(bodies[1]).toBe(bodies[0])
    wrapper.unmount()
  })

  it('keeps the accusation form when the save hits a version conflict', async () => {
    stubFetch({
      ...base,
      'GET /api/v1/sessions/current': () =>
        json(200, {
          current_session_id: id,
          session: view('ACCUSATION', null),
        }),
      [`PUT ${session}/accusation-draft`]: () =>
        json(409, {
          error: {
            code: 'STATE_VERSION_CONFLICT',
            message: '游戏进度已更新，请刷新后重试。',
            details: { current_state_version: 10 },
            retryable: false,
          },
        }),
    })
    const wrapper = await mountView()
    await wrapper.get('[data-testid="option-NPC02"]').trigger('click')
    const explanation = wrapper.get(
      '[data-testid="accusation-explanation"] textarea, textarea[data-testid="accusation-explanation"]',
    )
    await explanation.setValue('先记下这个想法')
    await wrapper.get('[data-testid="save-draft"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('游戏进度已更新')
    expect((explanation.element as HTMLTextAreaElement).value).toBe('先记下这个想法')
    wrapper.unmount()
  })
})
