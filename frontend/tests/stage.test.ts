// v2.0 week 1: the single stage, the HUD room switch and the dossier drawer.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import GameView from '../src/views/GameView.vue'
import { useGameStore } from '../src/stores/game'
import { caseSummary, json, npc, sessionView, stubFetch } from './fixtures'

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.unstubAllGlobals())

function twoRooms() {
  const view = sessionView()
  view.scenes.push({
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
    ],
  })
  view.npcs = [npc()]
  return view
}

async function mountView() {
  const view = twoRooms()
  stubFetch({
    'POST /api/v1/visitors': () => json(201, { current_session_id: view.session.session_id }),
    'GET /api/v1/cases': () => json(200, { items: [caseSummary] }),
    'GET /api/v1/sessions/current': () =>
      json(200, { current_session_id: view.session.session_id, session: view }),
  })
  const wrapper = mount(GameView, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

describe('single stage', () => {
  it('shows one room at a time and switches rooms from the HUD', async () => {
    const wrapper = await mountView()
    expect(wrapper.get('[data-testid="scene-S01"]').isVisible()).toBe(true)
    expect(wrapper.get('[data-testid="scene-S02"]').isVisible()).toBe(false)
    expect(wrapper.get('[data-testid="scene-tab-S02"]').text()).toContain('资料室 0/1')

    await wrapper.get('[data-testid="scene-tab-S02"]').trigger('click')
    expect(wrapper.get('[data-testid="scene-S01"]').isVisible()).toBe(false)
    expect(wrapper.get('[data-testid="scene-S02"]').isVisible()).toBe(true)
    expect(wrapper.get('[data-testid="scene-tab-S02"]').attributes('aria-pressed')).toBe('true')
    wrapper.unmount()
  })

  it('opens the dossier, closes it with Esc and returns focus to the trigger', async () => {
    const wrapper = await mountView()
    const dossier = wrapper.get('#dossier')
    const trigger = wrapper.get('[data-testid="dossier-evidence"]')
    expect(dossier.isVisible()).toBe(false)

    ;(trigger.element as HTMLElement).focus()
    await trigger.trigger('click')
    await flushPromises()
    expect(dossier.isVisible()).toBe(true)
    expect(trigger.attributes('aria-expanded')).toBe('true')
    expect(document.activeElement).toBe(dossier.element)

    await dossier.trigger('keydown', { key: 'Escape' })
    await flushPromises()
    expect(dossier.isVisible()).toBe(false)
    expect(document.activeElement).toBe(trigger.element)
    wrapper.unmount()
  })

  it('hands the stage to the interrogation and closes the dossier', async () => {
    const wrapper = await mountView()
    await wrapper.get('[data-testid="dossier-suspects"]').trigger('click')
    expect(wrapper.get('[data-testid="talk-NPC01"]').isVisible()).toBe(true)

    const game = useGameStore()
    game.view!.session.phase = 'INTERROGATION'
    game.view!.session.active_npc_id = 'NPC01'
    game.view!.npcs[0].is_active = true
    await flushPromises()
    expect(wrapper.get('#dossier').isVisible()).toBe(false)
    expect(wrapper.find('[data-testid="interrogation-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="scene-list"]').exists()).toBe(false)
    wrapper.unmount()
  })
})
