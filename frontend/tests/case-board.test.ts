// The relationship chart must appear once a board first mounted hidden (mobile tab) is shown.
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import CaseBoard from '../src/components/reasoning/CaseBoard.vue'
import { useGameStore } from '../src/stores/game'
import type { SessionView } from '../src/api/types'

const init = vi.hoisted(() =>
  vi.fn(() => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn() })),
)
vi.mock('echarts/core', () => ({ use: vi.fn(), init }))

describe('case board', () => {
  it('creates the chart when a hidden container gets a size', async () => {
    const pinia = createPinia()
    useGameStore(pinia).view = {
      session: { phase: 'INTERROGATION' },
      evidence: [],
      relationships: { nodes: [], edges: [] },
      timeline: { origin_label: '', items: [] },
    } as unknown as SessionView
    const wrapper = mount(CaseBoard, { global: { plugins: [pinia] }, attachTo: document.body })
    await flushPromises()
    expect(init).not.toHaveBeenCalled()
    const el = wrapper.get('[data-testid="relationship-graph"]').element
    Object.defineProperty(el, 'clientWidth', { value: 360 })
    Object.defineProperty(el, 'clientHeight', { value: 260 })
    window.dispatchEvent(new Event('resize'))
    expect(init).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })
})
