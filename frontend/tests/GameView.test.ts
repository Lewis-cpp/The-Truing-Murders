import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import GameView from '../src/views/GameView.vue'
import { caseSummary, json, sessionView, stubFetch } from './fixtures'

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.unstubAllGlobals())

const base = {
  'POST /api/v1/visitors': () => json(201, { current_session_id: null }),
  'GET /api/v1/cases': () => json(200, { items: [caseSummary] }),
}

function mountView() {
  return mount(GameView, { global: { plugins: [createPinia()] }, attachTo: document.body })
}

describe('game page', () => {
  it('offers the published case when there is no save', async () => {
    stubFetch({
      ...base,
      'GET /api/v1/sessions/current': () => json(200, { current_session_id: null, session: null }),
    })
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('停电之夜')
    expect(wrapper.text()).toContain('开始游戏')
    wrapper.unmount()
  })

  it('restores the current save from the server', async () => {
    const view = sessionView({ state_version: 4 })
    stubFetch({
      ...base,
      'GET /api/v1/sessions/current': () =>
        json(200, { current_session_id: view.session.session_id, session: view }),
    })
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('存档版本 4')
    expect(wrapper.text()).toContain('查看备用门禁终端')
    wrapper.unmount()
  })

  it('shows no success when saving fails and retries with the same key', async () => {
    const view = sessionView()
    const keys: string[] = []
    let attempts = 0
    const fetchMock = stubFetch({
      ...base,
      'GET /api/v1/sessions/current': () =>
        json(200, { current_session_id: view.session.session_id, session: view }),
      [`POST /api/v1/sessions/${view.session.session_id}/scenes/S01/investigations`]: (init) => {
        keys.push((init!.headers as Record<string, string>)['Idempotency-Key'])
        attempts += 1
        if (attempts === 1) {
          return json(503, {
            error: {
              code: 'PERSISTENCE_UNAVAILABLE',
              message: '存档服务暂不可用，本次操作未确认保存。',
              details: {},
              retryable: true,
            },
          })
        }
        return json(201, {
          ...view,
          result_state_version: 2,
          data: { outcome: { summary: '获得 E01 · 备用门禁记录' } },
        })
      },
    })
    const wrapper = mountView()
    await flushPromises()
    await wrapper
      .findAll('button')
      .find((b) => b.text() === '查看备用门禁终端')!
      .trigger('click')
    await flushPromises()
    expect(wrapper.get('.feedback.error').text()).toContain('未确认保存')
    expect(wrapper.get('[role="status"]').text()).toBe('')

    await wrapper
      .findAll('button')
      .find((b) => b.text() === '重试同一操作')!
      .trigger('click')
    await flushPromises()
    expect(keys).toHaveLength(2)
    expect(keys[1]).toBe(keys[0])
    expect(wrapper.get('[role="status"]').text()).toContain('获得 E01')
    expect(wrapper.find('.feedback.error').exists()).toBe(false)
    expect(fetchMock).toHaveBeenCalled()
    wrapper.unmount()
  })
})
