import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import App from '../src/App.vue'

afterEach(() => vi.unstubAllGlobals())

describe('development connection check', () => {
  it('shows success after the backend confirms the database connection', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: 'ok', database: 'ok' }),
      }),
    )
    const wrapper = mount(App)
    expect(wrapper.get('[role="status"]').text()).toContain('正在检查')
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toBe('前端、后端与数据库已连通。')
    wrapper.unmount()
  })

  it.each([
    { ok: false },
    { ok: true, json: async () => ({ status: 'ok', database: 'unavailable' }) },
  ])('does not report success for an unavailable database', async (response) => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response))
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toContain('连接失败')
    wrapper.unmount()
  })

  it('can retry after a network failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockRejectedValueOnce(new TypeError('Network error'))
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ status: 'ok', database: 'ok' }),
        }),
    )
    const wrapper = mount(App)
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toContain('连接失败')
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toBe('前端、后端与数据库已连通。')
    wrapper.unmount()
  })
})
