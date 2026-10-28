import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import permissions from '../generated/permissions.json'
import { SCREENS } from './moduleAccess'
import { ALL_TAGS, TAG_NAMES, TAGS, TAGS_WITHOUT_SCREEN } from './tags'

const APP_DIR = fileURLToPath(new URL('..', import.meta.url))
const actions = permissions.modules.flatMap((module) => module.actions)
const jsonTags = new Set(actions.map((action) => action.tag))
const assignable = actions.filter((action) => action.assignable).map((action) => action.tag)

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry)
    if (statSync(path).isDirectory()) return entry === 'generated' ? [] : sourceFiles(path)
    return /\.(ts|vue)$/.test(entry) && !entry.endsWith('.test.ts') ? [path] : []
  })
}

describe('alineación de tags con el contrato del backend (generated/permissions.json)', () => {
  it('todo tag literal del código fuente existe en el contrato', () => {
    const unknown: string[] = []
    for (const file of sourceFiles(APP_DIR)) {
      for (const tag of readFileSync(file, 'utf8').match(/incubus\.[a-z0-9-]+\.[a-z0-9-]+/g) ?? []) {
        if (!jsonTags.has(tag)) unknown.push(`${relative(APP_DIR, file)}: ${tag}`)
      }
    }
    expect(unknown).toEqual([])
  })

  it('todo tag de TAGS y de SCREENS existe en el contrato', () => {
    const used = [...Object.values(TAGS).flatMap((module) => Object.values(module)), ...SCREENS.map((s) => s.tag)]
    expect(used.filter((tag) => !jsonTags.has(tag))).toEqual([])
  })

  it('todo tag asignable del contrato está en TAGS/SCREENS o justificado en TAGS_WITHOUT_SCREEN', () => {
    const referenced = new Set([
      ...Object.values(TAGS).flatMap((module) => Object.values<string>(module)),
      ...SCREENS.map((screen) => screen.tag),
      ...Object.keys(TAGS_WITHOUT_SCREEN)
    ])
    expect(assignable.filter((tag) => !referenced.has(tag)), 'tags del backend sin alinear en el frontend').toEqual([])
    for (const [tag, reason] of Object.entries(TAGS_WITHOUT_SCREEN)) {
      expect(jsonTags.has(tag), tag).toBe(true)
      expect(reason.trim(), tag).not.toBe('')
    }
  })

  it('ALL_TAGS y los nombres legibles se derivan del contrato', () => {
    expect(ALL_TAGS).toEqual(assignable)
    expect(ALL_TAGS).not.toContain('incubus.settings.update')
    for (const action of actions) expect(TAG_NAMES[action.tag]).toBe(action.name)
  })
})
