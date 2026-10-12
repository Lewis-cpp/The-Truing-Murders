import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

// The build only bundles src/ and public/. Case files and answers live in backend/assets.
const roots = ['src', 'public'].map((dir) => join(__dirname, '..', dir))
const markers = ['"truth"', '"scoring"', '"admission_pressure_min"', 'B17', '利用工程检修']

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    return statSync(path).isDirectory() ? files(path) : [path]
  })
}

describe('frontend sources', () => {
  it('contain no case definitions or answers', () => {
    for (const path of roots.flatMap(files)) {
      expect(path.endsWith('.json'), path).toBe(false)
      const text = readFileSync(path, 'utf-8')
      for (const marker of markers)
        expect(text.includes(marker), `${marker} in ${path}`).toBe(false)
    }
  })
})
