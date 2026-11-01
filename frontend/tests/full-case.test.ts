// v0.3 acceptance: the fixed-mode page for the full case, via the data-testid contract.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import GameView from '../src/views/GameView.vue'
import type { SessionView } from '../src/api/types'
import { json, stubFetch } from './fixtures'

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.unstubAllGlobals())

const id = '00000000-0000-4000-8000-000000000003'
const session = `/api/v1/sessions/${id}`
const base = {
  'POST /api/v1/visitors': () => json(200, { current_session_id: id }),
  'GET /api/v1/cases': () =>
    json(200, {
      items: [
        {
          case_id: 'case_001',
          case_version: '3-full',
          title: '停电之夜',
          synopsis: '简介',
        },
      ],
    }),
}

const emptyDraft = {
  suspect_character_id: null,
  weapon_option_id: null,
  motive_option_id: null,
  ordered_process_step_ids: [],
  cited_evidence_ids: [],
  step_evidence_links: [],
  explanation: '',
}

function npc(npcId: string, name: string, extra: Record<string, unknown> = {}) {
  return {
    npc_id: npcId,
    name,
    public_identity: `${name}的身份`,
    is_contactable: true,
    is_active: false,
    is_evading: false,
    emotion: 'CALM',
    admission_progress: 'NONE',
    display_state: 'CALM',
    fixed_statement: null,
    presented_evidence_ids: [],
    known_statements: [],
    topics: [],
    ...extra,
  }
}

function view(phase = 'DEEP_INVESTIGATION', version = 7, extra: Record<string, unknown> = {}) {
  const actions =
    phase === 'ACCUSATION'
      ? ['SAVE_ACCUSATION_DRAFT', 'SUBMIT_ACCUSATION', 'CANCEL_ACCUSATION', 'RESTART']
      : ['INVESTIGATE', 'SET_INTERROGATION', 'OPEN_ACCUSATION', 'RESTART']
  return {
    session: {
      session_id: id,
      case_id: 'case_001',
      case_version: '3-full',
      title: '停电之夜',
      phase,
      state_version: version,
      active_npc_id: null,
      is_current: true,
      created_at: '2026-11-01T00:00:00Z',
      saved_at: '2026-11-01T00:00:00Z',
      closed_at: null,
      finished_at: null,
      available_actions: actions,
    },
    intro_text: '案发当晚。',
    scenes: [
      {
        scene_id: 'S01',
        name: '档案室',
        description: '桌面散着纸页。',
        visited: true,
        actions: [
          {
            action_id: 'A01',
            label: '查看备用门禁终端',
            completed: true,
            enabled: true,
            disabled_reason: null,
          },
        ],
      },
      {
        scene_id: 'S02',
        name: '资料室',
        description: '借阅柜台。',
        visited: false,
        actions: [
          {
            action_id: 'A05',
            label: '翻阅借阅簿',
            completed: false,
            enabled: true,
            disabled_reason: null,
          },
          {
            action_id: 'A06',
            label: '核对复印任务',
            completed: false,
            enabled: false,
            disabled_reason: '核对条件尚不齐全。',
          },
        ],
      },
    ],
    evidence: [
      {
        evidence_id: 'E01',
        name: '备用门禁记录',
        kind: 'DIGITAL',
        content: '21:10 进入。',
        source: { kind: 'SCENE', id: 'S01', label: '备用终端' },
        credibility: 'VERIFIED',
        discovered_at: '2026-11-01T00:00:00Z',
        key_badge: false,
        known_conflicts: [],
        links: [],
      },
    ],
    npcs: [
      npc('NPC01', '沈砚', {
        display_state: 'PARTIAL_CONFESSION',
        admission_progress: 'PARTIAL_CONFESSION',
      }),
      npc('NPC02', '许岚'),
      npc('NPC03', '周启', { display_state: 'NERVOUS', emotion: 'NERVOUS' }),
      npc('NPC04', '林澄', {
        topics: [{ topic_id: 'Q04', label: '你复制过 B17 的数据吗？', asked: false }],
      }),
    ],
    known_information: [],
    relationships: {
      nodes: [
        {
          character_id: 'NPC01',
          name: '沈砚',
          role: '副研究员',
          public_identity: '副研究员',
        },
        {
          character_id: 'VICTIM',
          name: '陆衡',
          role: '研究所负责人',
          public_identity: '负责人',
        },
      ],
      edges: [
        {
          relationship_id: 'R01',
          from_character_id: 'NPC01',
          to_character_id: 'VICTIM',
          relationship_type: '下属',
          directed: true,
          description: '沈砚是陆衡的下属。',
          assertion_kind: 'FACT',
          source: { kind: 'PUBLIC', id: null, label: '案件公开信息' },
          credibility: 'VERIFIED',
          discovered_at: null,
          known_conflicts: [],
        },
      ],
    },
    timeline: {
      origin_label: '案发当日 00:00',
      items: [
        {
          timeline_event_id: 'T06',
          title: '沈砚进出档案室',
          description: '门禁记录。',
          scene_id: 'S01',
          participant_ids: ['NPC01'],
          time_precision: 'RANGE',
          time_start_minutes: 1270,
          time_end_minutes: 1276,
          time_label: '21:10—21:16',
          assertion_kind: 'FACT',
          source: { kind: 'EVIDENCE', id: 'E01', label: '备用门禁记录' },
          credibility: 'VERIFIED',
          discovered_at: '2026-11-01T00:00:00Z',
          known_conflicts: [],
        },
        {
          timeline_event_id: 'T07',
          title: '沈砚供述袭击陆衡',
          description: '未说明具体分钟。',
          scene_id: 'S01',
          participant_ids: ['NPC01', 'VICTIM'],
          time_precision: 'UNKNOWN',
          time_start_minutes: null,
          time_end_minutes: null,
          time_label: '门禁记录时段内，具体时间未知',
          assertion_kind: 'TESTIMONY',
          source: { kind: 'NPC', id: 'NPC01', label: '沈砚' },
          credibility: 'UNVERIFIED',
          discovered_at: '2026-11-01T00:00:00Z',
          known_conflicts: [],
        },
      ],
    },
    accusation_options: {
      suspects: [
        { id: 'NPC01', label: '沈砚 · 副研究员' },
        { id: 'NPC02', label: '许岚 · 档案管理员' },
      ],
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
    ...extra,
  } as unknown as SessionView
}

function current(v: SessionView) {
  return () => json(200, { current_session_id: id, session: v })
}

function result(data: unknown, version: number, phase = 'DEEP_INVESTIGATION') {
  return {
    request_id: 'r',
    session_id: id,
    business_status: 'COMMITTED',
    state_changed: true,
    state_version_before: version - 1,
    result_state_version: version,
    phase_after: phase,
    active_npc_id_after: null,
    saved_at: '2026-11-01T00:00:00Z',
    data,
    conversation: null,
  }
}

function headers(init: RequestInit | undefined) {
  return init!.headers as Record<string, string>
}

async function mountView() {
  const wrapper = mount(GameView, {
    global: { plugins: [createPinia()] },
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

function byTestId(wrapper: VueWrapper, testId: string) {
  return wrapper.get(`[data-testid="${testId}"]`)
}

describe('full case page', () => {
  it('lists open scenes, four people, relationships and timeline without numbers', async () => {
    stubFetch({ ...base, 'GET /api/v1/sessions/current': current(view()) })
    const wrapper = await mountView()
    expect(byTestId(wrapper, 'scene-list').findAll('[data-testid^="scene-S"]')).toHaveLength(2)
    expect(byTestId(wrapper, 'action-A06').attributes('disabled')).toBeDefined()
    expect(byTestId(wrapper, 'scene-S02').text()).toContain('核对条件尚不齐全。')
    const npcs = byTestId(wrapper, 'npc-list').findAll('[data-testid^="npc-NPC"]')
    expect(npcs).toHaveLength(4)
    expect(byTestId(wrapper, 'npc-NPC01').text()).not.toMatch(/\d{2}/)
    expect(byTestId(wrapper, 'relationship-list').text()).toContain('沈砚是陆衡的下属。')
    expect(wrapper.find('[data-testid="relationship-R01"]').exists()).toBe(true)
    expect(byTestId(wrapper, 'timeline-T07').text()).toContain('门禁记录时段内，具体时间未知')
    expect(byTestId(wrapper, 'timeline-T06').text()).toContain('21:10—21:16')
    const order = byTestId(wrapper, 'timeline-list')
      .findAll('[data-testid^="timeline-T"]')
      .map((item) => item.attributes('data-testid'))
    expect(order).toEqual(['timeline-T06', 'timeline-T07'])
    wrapper.unmount()
  })

  it('investigates in the scene that owns the action', async () => {
    const sentTo: string[] = []
    stubFetch({
      ...base,
      'GET /api/v1/sessions/current': current(view()),
      [`POST ${session}/scenes/S02/investigations`]: (init) => {
        sentTo.push(
          `${JSON.parse(init!.body as string).action_id}@${headers(init)['X-Expected-State-Version']}`,
        )
        return json(
          201,
          result(
            {
              outcome: {
                reason_code: 'PROGRESS_UPDATED',
                summary: '获得 E05 · 借阅簿',
              },
            },
            8,
          ),
        )
      },
    })
    const wrapper = await mountView()
    await byTestId(wrapper, 'action-A05').trigger('click')
    await flushPromises()
    expect(sentTo).toEqual(['A05@7'])
    expect(wrapper.get('[role="status"]').text()).toContain('获得 E05')
    wrapper.unmount()
  })

  it('opens evidence details from the bag', async () => {
    stubFetch({ ...base, 'GET /api/v1/sessions/current': current(view()) })
    const wrapper = await mountView()
    await byTestId(wrapper, 'evidence-E01').trigger('click')
    await flushPromises()
    expect(byTestId(wrapper, 'evidence-detail').text()).toContain('21:10 进入。')
    expect(byTestId(wrapper, 'evidence-detail').text()).toContain('备用终端')
    wrapper.unmount()
  })

  it('shows the conversation log of the active person', async () => {
    const talking = view('INTERROGATION', 9)
    talking.session.active_npc_id = 'NPC04'
    talking.session.available_actions = [
      'SET_INTERROGATION',
      'END_INTERROGATION',
      'CHAT',
      'PRESENT_EVIDENCE',
      'OPEN_ACCUSATION',
      'RESTART',
    ]
    ;(talking.npcs[3] as unknown as Record<string, unknown>).is_active = true
    ;(talking.npcs[3] as unknown as Record<string, unknown>).fixed_statement =
      '我只能说明已核对的记录。'
    const round = (seq: number, question: string) => ({
      conversation_id: `00000000-0000-4000-8000-00000000010${seq}`,
      conversation_seq: seq,
      session_id: id,
      npc_id: 'NPC04',
      request_id: `00000000-0000-4000-8000-00000000020${seq}`,
      interaction_type: 'CHAT',
      source_state_version: 9,
      generation_status: 'FALLBACK',
      generation_deadline_at: null,
      deadline_exceeded: false,
      fixed_reply: '我只能说明已核对的记录。',
      messages: [
        {
          message_id: `p${seq}`,
          sequence_no: 1,
          speaker: 'PLAYER',
          content: question,
          origin: 'PLAYER',
          validity: 'VALID',
          created_at: '2026-11-01T00:00:00Z',
          updated_at: '2026-11-01T00:00:00Z',
        },
        {
          message_id: `n${seq}`,
          sequence_no: 2,
          speaker: 'NPC',
          content: '我只能说明已核对的记录。',
          origin: 'FIXED',
          validity: 'VALID',
          created_at: '2026-11-01T00:00:00Z',
          updated_at: '2026-11-01T00:00:00Z',
        },
      ],
      fallback_reason: 'GENERATION_DISABLED',
      can_retry_reply: false,
      created_at: '2026-11-01T00:00:00Z',
      completed_at: '2026-11-01T00:00:00Z',
    })
    stubFetch({
      ...base,
      'GET /api/v1/sessions/current': current(talking),
      [`GET ${session}/npcs/NPC04/conversations?limit=20`]: () =>
        json(200, {
          session_id: id,
          state_version: 9,
          data: {
            items: [round(2, '第二问'), round(1, '第一问')],
            next_before_seq: null,
          },
        }),
    })
    const wrapper = await mountView()
    const log = byTestId(wrapper, 'conversation-log').text()
    expect(log.indexOf('第一问')).toBeGreaterThan(-1)
    expect(log.indexOf('第一问')).toBeLessThan(log.indexOf('第二问'))
    expect(byTestId(wrapper, 'interrogation-panel').text()).toContain('我只能说明已核对的记录。')
    expect(wrapper.find('[data-testid="topic-Q04"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="chat-input"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('saves a partial draft and keeps the form when submission is incomplete', async () => {
    const accusing = view('ACCUSATION', 10)
    const drafts: unknown[] = []
    let submitted = 0
    stubFetch({
      ...base,
      'GET /api/v1/sessions/current': current(accusing),
      [`PUT ${session}/accusation-draft`]: (init) => {
        drafts.push(JSON.parse(init!.body as string))
        return json(
          200,
          result({ content: { ...emptyDraft, suspect_character_id: 'NPC02' } }, 11, 'ACCUSATION'),
        )
      },
      [`POST ${session}/accusation`]: () => {
        submitted += 1
        return json(422, {
          error: {
            code: 'ACCUSATION_INCOMPLETE',
            message: '请补全凶器、动机和过程步骤。',
            details: {},
            retryable: false,
          },
        })
      },
    })
    const wrapper = await mountView()
    const form = byTestId(wrapper, 'accusation-form')
    expect(form.exists()).toBe(true)
    const store = (await import('../src/stores/game')).useGameStore()
    expect(store.view?.accusation_draft).toEqual(emptyDraft)
    await byTestId(wrapper, 'save-draft').trigger('click')
    await flushPromises()
    expect(drafts).toHaveLength(1)
    expect(Object.keys((drafts[0] as { content: object }).content).sort()).toEqual(
      Object.keys(emptyDraft).sort(),
    )
    expect(byTestId(wrapper, 'submit-accusation').attributes('disabled')).toBeDefined()
    await byTestId(wrapper, 'confirm-accusation').find('input').setValue(true)
    await flushPromises()
    expect(byTestId(wrapper, 'submit-accusation').attributes('disabled')).toBeUndefined()
    await byTestId(wrapper, 'submit-accusation').trigger('click')
    await flushPromises()
    expect(submitted).toBe(1)
    expect(byTestId(wrapper, 'accusation-form').text()).toContain('请补全')
    expect(wrapper.find('[data-testid="review-panel"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('shows criteria with missing evidence in the review', async () => {
    const closed = view('REVIEW', 12)
    closed.session.closed_at = '2026-11-01T01:00:00Z'
    closed.session.available_actions = ['FINISH_REVIEW', 'RESTART']
    stubFetch({
      ...base,
      'GET /api/v1/sessions/current': current(closed),
      [`GET ${session}/review`]: () =>
        json(200, {
          session_id: id,
          state_version: 12,
          data: {
            accusation: {
              content: emptyDraft,
              submitted_at: '2026-11-01T01:00:00Z',
              submitted_state_version: 11,
              case_version: '3-full',
              rules_version: 'full-1',
              verdict: {
                category: 'CORRECT',
                score: '90.00',
                max_score: '100.00',
                fixed_explanation: '推理成立：凶手、凶器、动机与关键依据基本吻合。',
                criteria: [
                  {
                    criterion_id: 'C_ENTRY',
                    label: '到场依据',
                    matched: false,
                    score: '0.00',
                    max_score: '10.00',
                    explanation: '未命中：需要独立校时。',
                    missing_evidence_ids: ['E11'],
                  },
                ],
              },
            },
            truth: {
              suspect_character_id: 'NPC01',
              weapon_option_id: 'W01',
              motive_option_id: 'M01',
              ordered_process_step_ids: ['P_ENTER'],
              labels: { NPC01: '沈砚 · 副研究员' },
              explanation: '复盘真相。',
            },
            evidence_chain: [],
            missed_evidence: [
              {
                evidence_id: 'E12',
                name: '值班通话记录',
                content: '21:25。',
                source: { kind: 'SCENE', id: 'S04', label: '值班台' },
                was_discovered: false,
              },
            ],
            fixed_review: '固定复盘。',
          },
        }),
    })
    const wrapper = await mountView()
    const review = byTestId(wrapper, 'review-panel').text()
    expect(review).toContain('90.00')
    expect(review).toContain('E11')
    expect(review).toContain('推理成立')
    expect(review).toContain('值班通话记录')
    wrapper.unmount()
  })
})
