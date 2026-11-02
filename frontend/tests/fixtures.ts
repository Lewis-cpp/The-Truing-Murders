import { vi } from 'vitest'
import type { ConversationView, EvidenceView, NpcView, SessionView } from '../src/api/types'

export const caseSummary = {
  case_id: 'case_001',
  case_version: '3-full',
  title: '停电之夜',
  synopsis: '简介',
}

export function emptyDraft(): SessionView['accusation_draft'] {
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

export function npc(overrides: Partial<NpcView> = {}): NpcView {
  return {
    npc_id: 'NPC01',
    name: '甲',
    public_identity: '研究员',
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
    ...overrides,
  }
}

export function evidence(overrides: Partial<EvidenceView> = {}): EvidenceView {
  return {
    evidence_id: 'E03',
    name: '移交联',
    kind: 'DOCUMENT',
    content: '缺失清单。',
    source: { kind: 'SCENE', id: 'S01', label: '档案柜' },
    credibility: 'VERIFIED',
    discovered_at: '2026-10-12T00:00:00Z',
    key_badge: false,
    known_conflicts: [],
    links: [],
    ...overrides,
  }
}

export function sessionView(overrides: Partial<SessionView['session']> = {}): SessionView {
  return {
    session: {
      session_id: '00000000-0000-4000-8000-000000000001',
      case_id: 'case_001',
      case_version: '3-full',
      title: '停电之夜',
      phase: 'INVESTIGATION',
      state_version: 1,
      active_npc_id: null,
      is_current: true,
      created_at: '2026-10-12T00:00:00Z',
      saved_at: '2026-10-12T00:00:00Z',
      closed_at: null,
      finished_at: null,
      available_actions: ['INVESTIGATE', 'SET_INTERROGATION', 'OPEN_ACCUSATION', 'RESTART'],
      ...overrides,
    },
    intro_text: '案发当晚。',
    scenes: [
      {
        scene_id: 'S01',
        name: '档案室',
        description: '桌面散着纸页。',
        visited: false,
        actions: [
          {
            action_id: 'A01',
            label: '查看备用门禁终端',
            completed: false,
            enabled: true,
            disabled_reason: null,
          },
        ],
      },
    ],
    evidence: [],
    npcs: [],
    known_information: [],
    relationships: { nodes: [], edges: [] },
    timeline: { origin_label: '案发当日 00:00', items: [] },
    accusation_options: {
      suspects: [],
      weapons: [],
      motives: [],
      process_steps: [],
      process_constraints: { min_steps: 1, max_steps: 5, allow_repeated_steps: false },
    },
    accusation_draft: emptyDraft(),
    pending_conversations: [],
  }
}

export function conversation(
  seq: number,
  question: string,
  reply: string,
  npcId = 'NPC01',
): ConversationView {
  const id = String(seq).padStart(3, '0')
  return {
    conversation_id: `00000000-0000-4000-8000-0000000001${id}`,
    conversation_seq: seq,
    session_id: '00000000-0000-4000-8000-000000000001',
    npc_id: npcId,
    request_id: `00000000-0000-4000-8000-0000000002${id}`,
    interaction_type: 'CHAT',
    source_state_version: 5,
    generation_status: 'FALLBACK',
    generation_deadline_at: null,
    deadline_exceeded: false,
    fixed_reply: reply,
    messages: [
      {
        message_id: `p${seq}`,
        sequence_no: 1,
        speaker: 'PLAYER',
        content: question,
        origin: 'PLAYER',
        validity: 'VALID',
        created_at: '2026-10-12T00:00:00Z',
        updated_at: '2026-10-12T00:00:00Z',
      },
      {
        message_id: `n${seq}`,
        sequence_no: 2,
        speaker: 'NPC',
        content: reply,
        origin: 'FIXED',
        validity: 'VALID',
        created_at: '2026-10-12T00:00:00Z',
        updated_at: '2026-10-12T00:00:00Z',
      },
    ],
    fallback_reason: 'GENERATION_DISABLED',
    can_retry_reply: false,
    created_at: '2026-10-12T00:00:00Z',
    completed_at: '2026-10-12T00:00:00Z',
  }
}

export function conversationPage(items: ConversationView[]) {
  return json(200, {
    session_id: '00000000-0000-4000-8000-000000000001',
    state_version: 5,
    data: { items, next_before_seq: null },
  })
}

export function json(status: number, body: unknown) {
  return { ok: status < 400, status, json: async () => body } as Response
}

type Handler = (init: RequestInit | undefined) => Response | Promise<Response>

/** A fetch stub keyed by "METHOD path"; unmatched calls fail the test loudly. */
export function stubFetch(routes: Record<string, Handler>) {
  const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
    const key = `${init?.method ?? 'GET'} ${input}`
    const handler = routes[key] ?? routes[`${init?.method ?? 'GET'} *`]
    if (!handler) throw new Error(`Unexpected request ${key}`)
    return handler(init)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}
