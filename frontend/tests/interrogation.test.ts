import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { ElOption, ElPopconfirm, ElSelect } from 'element-plus'
import GameView from '../src/views/GameView.vue'
import type { KnownInformation, NpcView, SessionView } from '../src/api/types'
import { caseSummary, json, sessionView, stubFetch } from './fixtures'

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.unstubAllGlobals())

const base = {
  'POST /api/v1/visitors': () => json(201, { current_session_id: null }),
  'GET /api/v1/cases': () => json(200, { items: [caseSummary] }),
}
const session = '/api/v1/sessions/00000000-0000-4000-8000-000000000001'

function npc(overrides: Partial<NpcView> = {}): NpcView {
  return {
    npc_id: 'NPC01',
    name: '甲',
    public_identity: '研究员',
    is_contactable: true,
    is_active: true,
    is_evading: false,
    emotion: 'CALM',
    admission_progress: 'NONE',
    display_state: 'CALM',
    fixed_statement: '我一直在休息区。',
    presented_evidence_ids: [],
    topics: [{ topic_id: 'Q01', label: '丢了什么？', asked: false }],
    ...overrides,
  }
}

function testimony(id: string, kind: string, sourceId: string | null): KnownInformation {
  return {
    information_ref: { kind: 'KNOWLEDGE', id },
    content: `${id} 的内容`,
    assertion_kind: 'TESTIMONY',
    source: { kind, id: sourceId, label: kind === 'NPC' ? '甲' : '案件公开信息' },
    credibility: 'UNVERIFIED',
    discovered_at: null,
  }
}

function interrogation(state: Partial<NpcView> = {}, version = 5): SessionView {
  const view = sessionView({
    phase: 'INTERROGATION',
    state_version: version,
    active_npc_id: 'NPC01',
    available_actions: [
      'SET_INTERROGATION',
      'END_INTERROGATION',
      'CHAT',
      'ASK_TOPIC',
      'PRESENT_EVIDENCE',
      'POINT_CONTRADICTION',
      'OPEN_ACCUSATION',
      'RESTART',
    ],
  })
  view.npcs = [npc(state)]
  view.evidence = [
    {
      evidence_id: 'E03',
      name: '移交联',
      content: '缺失清单。',
      source: { kind: 'SCENE', id: 'S01', label: '档案柜' },
      credibility: 'VERIFIED',
      discovered_at: '2026-10-12T00:00:00Z',
    },
  ]
  return view
}

function result(data: unknown, version = 6) {
  return {
    request_id: 'r',
    session_id: '00000000-0000-4000-8000-000000000001',
    business_status: 'COMMITTED',
    state_changed: true,
    state_version_before: version - 1,
    result_state_version: version,
    phase_after: 'INTERROGATION',
    saved_at: '2026-10-12T00:00:00Z',
    data,
  }
}

/** Serves the given views in order; the last one repeats. */
function views(...items: SessionView[]) {
  return () => {
    const view = items.length > 1 ? items.shift()! : items[0]
    return json(200, { current_session_id: view.session.session_id, session: view })
  }
}

function sent(init: RequestInit | undefined) {
  const headers = init!.headers as Record<string, string>
  return { body: JSON.parse(init!.body as string), version: headers['X-Expected-State-Version'] }
}

function button(wrapper: VueWrapper, text: string) {
  return wrapper.findAll('button').find((b) => b.text() === text)!
}

async function mountView() {
  const wrapper = mount(GameView, { global: { plugins: [createPinia()] }, attachTo: document.body })
  await flushPromises()
  return wrapper
}

describe('interrogation', () => {
  it('asks a topic and records the answer as unverified testimony', async () => {
    const after = interrogation({ topics: [{ topic_id: 'Q01', label: '丢了什么？', asked: true }] })
    after.known_information = [testimony('K03', 'NPC', 'NPC01')]
    const requests: ReturnType<typeof sent>[] = []
    stubFetch({
      ...base,
      'GET /api/v1/sessions/current': views(interrogation(), after),
      [`POST ${session}/npcs/NPC01/questions`]: (init) => {
        requests.push(sent(init))
        return json(
          201,
          result({
            fixed_reply: '肯定是被偷了。',
            outcome: { reason_code: 'TESTIMONY_RECORDED', summary: '证词已记录（未经核验）。' },
          }),
        )
      },
    })
    const wrapper = await mountView()
    await button(wrapper, '丢了什么？').trigger('click')
    await flushPromises()
    expect(requests).toEqual([{ body: { topic_id: 'Q01' }, version: '5' }])
    expect(wrapper.get('[role="status"]').text()).toContain('证词已记录')
    expect(wrapper.text()).toContain('甲：肯定是被偷了。')
    expect(button(wrapper, '丢了什么？（已问）').exists()).toBe(true)
    expect(wrapper.text()).toContain('K03 的内容')
    wrapper.unmount()
  })

  it('points out a contradiction between this NPC’s testimony and held evidence', async () => {
    const view = interrogation()
    view.known_information = [
      testimony('K01', 'PUBLIC', null),
      testimony('K03', 'NPC', 'NPC01'),
      testimony('K09', 'NPC', 'NPC02'),
    ]
    const requests: ReturnType<typeof sent>[] = []
    stubFetch({
      ...base,
      'GET /api/v1/sessions/current': views(view),
      [`POST ${session}/npcs/NPC01/contradictions`]: (init) => {
        requests.push(sent(init))
        return json(
          201,
          result({
            fixed_reply: '……我是猜的。',
            outcome: { reason_code: 'CONTRADICTION_CONFIRMED', summary: '矛盾成立：清单未公布。' },
          }),
        )
      },
    })
    const wrapper = await mountView()
    expect(button(wrapper, '指出矛盾').attributes('disabled')).toBeDefined()
    const [, cited, against] = wrapper.findAllComponents(ElSelect)
    const citable = cited.findAllComponents(ElOption).map((option) => option.props('value'))
    expect(citable).toEqual(['K03'])
    cited.vm.$emit('update:modelValue', 'K03')
    against.vm.$emit('update:modelValue', 'E03')
    await flushPromises()
    await button(wrapper, '指出矛盾').trigger('click')
    await flushPromises()
    expect(requests).toEqual([{ body: { knowledge_id: 'K03', evidence_id: 'E03' }, version: '5' }])
    expect(wrapper.find('[role="status"] .el-alert--success').text()).toContain('矛盾成立')
    expect(wrapper.text()).toContain('甲：……我是猜的。')
    wrapper.unmount()
  })

  it('warns about irrelevant moves and evasion, and clears the transcript on leaving', async () => {
    const evading = interrogation({ is_evading: true, display_state: 'EVADING' })
    const left = sessionView({ phase: 'DEEP_INVESTIGATION', state_version: 7 })
    left.npcs = [npc({ is_active: false, fixed_statement: null })]
    stubFetch({
      ...base,
      'GET /api/v1/sessions/current': views(interrogation(), evading, left, interrogation({}, 8)),
      [`POST ${session}/npcs/NPC01/evidence-presentations`]: () =>
        json(
          201,
          result({
            fixed_reply: '我现在不想再谈了。',
            outcome: { reason_code: 'NPC_EVADING', summary: '甲开始回避；结束审讯后再来。' },
          }),
        ),
      [`DELETE ${session}/interrogation`]: () => json(200, result({}, 7)),
      [`PUT ${session}/interrogation`]: () => json(201, result({}, 8)),
    })
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('接连这样做，对方会开始回避')
    wrapper.findAllComponents(ElSelect)[0].vm.$emit('update:modelValue', 'E03')
    await flushPromises()
    await button(wrapper, '出示').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="status"] .el-alert--warning').text()).toContain('开始回避')
    expect(wrapper.find('.npc .el-tag').text()).toBe('回避')
    expect(wrapper.text()).toContain('甲在回避，暂时问不出什么。结束审讯后再来。')
    expect(wrapper.findAll('.reply').map((reply) => reply.text())).toEqual([
      '甲：我现在不想再谈了。',
    ])
    await button(wrapper, '结束审讯').trigger('click')
    await flushPromises()
    await button(wrapper, '审讯').trigger('click')
    await flushPromises()
    expect(wrapper.text()).not.toContain('在回避')
    expect(wrapper.findAll('.reply')).toHaveLength(0)
    wrapper.unmount()
  })
})

describe('unreadable save', () => {
  const unsupported = () =>
    json(409, {
      error: {
        code: 'SAVE_VERSION_UNSUPPORTED',
        message: '当前版本暂时无法读取此存档。存档已保留，可以返回大厅开始新的一局。',
        details: { session_id: 'old-session', state_version: 7 },
        retryable: false,
      },
    })

  it('is kept and replaced by a new game only after confirmation', async () => {
    const requests: ReturnType<typeof sent>[] = []
    const fresh = sessionView()
    let current = unsupported
    stubFetch({
      ...base,
      'GET /api/v1/sessions/current': () => current(),
      'POST /api/v1/sessions': (init) => {
        requests.push(sent(init))
        current = () => json(200, { current_session_id: fresh.session.session_id, session: fresh })
        return json(201, result(fresh, 1))
      },
    })
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('当前版本暂时无法读取此存档')
    expect(wrapper.find('.feedback.error').exists()).toBe(false)
    await button(wrapper, '开始新的一局').trigger('click')
    await flushPromises()
    expect(requests).toHaveLength(0)
    wrapper.findComponent(ElPopconfirm).vm.$emit('confirm')
    await flushPromises()
    expect(requests).toEqual([
      {
        body: {
          case_id: 'case_001',
          case_version: '2-slice',
          replaces_session_id: 'old-session',
          confirm_restart: true,
        },
        version: '7',
      },
    ])
    expect(wrapper.text()).not.toContain('无法读取')
    expect(wrapper.text()).toContain('查看备用门禁终端')
    wrapper.unmount()
  })

  it.each(['database', 'network'])(
    'shows a restart %s failure and retries the same request',
    async (failure) => {
      const fresh = sessionView()
      let current = unsupported
      const requests: (ReturnType<typeof sent> & { key: string })[] = []
      stubFetch({
        ...base,
        'GET /api/v1/sessions/current': () => current(),
        'GET *': () => Promise.reject(new TypeError('network')),
        'POST /api/v1/sessions': (init) => {
          requests.push({
            ...sent(init),
            key: (init!.headers as Record<string, string>)['Idempotency-Key'],
          })
          if (requests.length === 1) {
            if (failure === 'network') return Promise.reject(new TypeError('network'))
            return json(503, {
              error: {
                code: 'PERSISTENCE_UNAVAILABLE',
                message: '存档服务暂不可用，本次操作未确认保存。',
                details: {},
                retryable: true,
              },
            })
          }
          current = () =>
            json(200, { current_session_id: fresh.session.session_id, session: fresh })
          return json(201, result(fresh, 1))
        },
      })
      const wrapper = await mountView()
      wrapper.findComponent(ElPopconfirm).vm.$emit('confirm', new MouseEvent('click'))
      await flushPromises()
      expect(wrapper.get('.feedback.error').text()).toContain(
        failure === 'network' ? '网络中断' : '未确认保存',
      )
      expect(wrapper.get('[role="status"]').text()).toBe('')
      expect(wrapper.text()).toContain('当前版本暂时无法读取此存档')

      await button(wrapper, '重试同一操作').trigger('click')
      await flushPromises()
      expect(requests).toHaveLength(2)
      expect(requests[0].key).toBeTruthy()
      expect(requests[1]).toEqual(requests[0])
      expect(wrapper.find('.feedback.error').exists()).toBe(false)
      expect(wrapper.text()).not.toContain('无法读取')
      expect(wrapper.text()).toContain('查看备用门禁终端')
      wrapper.unmount()
    },
  )

  it('sends the player to the lobby when the server stops reading the save mid-game', async () => {
    const view = sessionView()
    let current = () => json(200, { current_session_id: view.session.session_id, session: view })
    stubFetch({
      ...base,
      'GET /api/v1/sessions/current': () => current(),
      [`POST ${session}/scenes/S01/investigations`]: () => {
        current = unsupported
        return unsupported()
      },
    })
    const wrapper = await mountView()
    await button(wrapper, '查看备用门禁终端').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('当前版本暂时无法读取此存档')
    expect(wrapper.find('.feedback.error').exists()).toBe(false)
    expect(button(wrapper, '开始新的一局').exists()).toBe(true)
    wrapper.unmount()
  })
})
