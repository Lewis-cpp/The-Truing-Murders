import { vi } from 'vitest'
import type { SessionView } from '../src/api/types'

export const caseSummary = {
  case_id: 'case_001',
  case_version: '1-slice',
  title: '停电之夜',
  synopsis: '简介',
}

export function sessionView(overrides: Partial<SessionView['session']> = {}): SessionView {
  return {
    session: {
      session_id: '00000000-0000-4000-8000-000000000001',
      case_id: 'case_001',
      case_version: '1-slice',
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
    accusation_options: {
      suspects: [],
      weapons: [],
      motives: [],
      process_steps: [],
      process_constraints: { min_steps: 1, max_steps: 5, allow_repeated_steps: false },
    },
  }
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
