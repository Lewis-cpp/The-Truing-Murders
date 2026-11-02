// v1.0 acceptance: announcements, text labels and motion variables in the component tree.
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import GameView from '../src/views/GameView.vue'
import { json, stubFetch } from './fixtures'

beforeEach(() => setActivePinia(createPinia()))
afterEach(() => vi.unstubAllGlobals())

describe('accessibility', () => {
  it('announces results politely and has named buttons on the lobby', async () => {
    stubFetch({
      'POST /api/v1/visitors': () => json(201, { current_session_id: null }),
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
      'GET /api/v1/sessions/current': () => json(200, { current_session_id: null, session: null }),
    })
    const wrapper = mount(GameView, {
      global: { plugins: [createPinia()] },
      attachTo: document.body,
    })
    await flushPromises()
    const status = wrapper.get('[role="status"]')
    expect(status.attributes('aria-live')).toBe('polite')
    for (const button of wrapper.findAll('button')) {
      const name = button.text().trim() || button.attributes('aria-label') || ''
      expect(name.length, button.html()).toBeGreaterThan(0)
    }
    wrapper.unmount()
  })

  it('defines one motion variable that reduced motion switches off', () => {
    const css = readFileSync(join(__dirname, '../src/styles/theme.css'), 'utf-8')
    expect(css).toMatch(/--tm-motion-duration:\s*\d+ms/)
    expect(css).toMatch(
      /@media\s*\(prefers-reduced-motion:\s*reduce\)[\s\S]*--tm-motion-duration:\s*0(ms|s)?/,
    )
  })
})
