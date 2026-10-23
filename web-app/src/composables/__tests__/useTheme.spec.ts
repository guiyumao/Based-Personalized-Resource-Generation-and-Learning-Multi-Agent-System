import { beforeEach, describe, expect, it } from 'vitest'
import { useTheme } from '../useTheme'

const theme = useTheme()
beforeEach(() => { theme.setTheme(null); theme.init() })
function changed(key: string | null, value: string | null, storageArea = localStorage) {
  window.dispatchEvent(new StorageEvent('storage', { key, newValue: value, storageArea }))
}
describe('shared appearance across public pages and workspaces', () => {
  it('all consumers share the selected theme and persist it', () => {
    theme.setTheme('ocean')
    expect(useTheme().currentTheme.value).toBe('ocean')
    expect(document.documentElement.dataset.theme).toBe('ocean')
    expect(localStorage.getItem('app-theme')).toBe('ocean')
    theme.init()
    expect(theme.currentTheme.value).toBe('ocean')
  })
  it('applies a theme selected in another tab without writing it back', () => {
    changed('app-theme', 'cosmic')
    expect(theme.currentTheme.value).toBe('cosmic')
    expect(document.documentElement.dataset.theme).toBe('cosmic')
    expect(localStorage.getItem('app-theme')).toBeNull()
  })
  it('resets every consumer when another tab restores the default or clears storage', () => {
    theme.setTheme('forest'); changed('app-theme', null)
    expect(theme.currentTheme.value).toBeNull()
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
    theme.setTheme('warm'); changed(null, null)
    expect(theme.currentTheme.value).toBeNull()
  })
  it('ignores auth and session storage events and rejects unknown themes', () => {
    theme.setTheme('minimal')
    changed('learning-system-auth', 'ocean')
    changed('app-theme', 'ocean', sessionStorage)
    expect(theme.currentTheme.value).toBe('minimal')
    changed('app-theme', 'invalid')
    expect(theme.currentTheme.value).toBeNull()
  })
})
