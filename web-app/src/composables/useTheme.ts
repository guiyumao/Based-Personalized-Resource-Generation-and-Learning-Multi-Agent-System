import { ref } from 'vue'

const THEME_STORAGE_KEY = 'app-theme'
export type ThemeName = 'ocean' | 'warm' | 'cosmic' | 'minimal' | 'forest' | null

const THEME_LIST: ThemeName[] = ['ocean', 'warm', 'cosmic', 'minimal', 'forest']

const currentTheme = ref<ThemeName>(null)

export function useTheme() {
  function init() {
    const stored = localStorage.getItem(THEME_STORAGE_KEY) as ThemeName | null
    if (stored && THEME_LIST.includes(stored)) {
      applyTheme(stored)
    }
    if (!stored) {
      currentTheme.value = null
      document.documentElement.removeAttribute('data-theme')
    }
  }

  function setTheme(theme: ThemeName) {
    if (theme && THEME_LIST.includes(theme)) {
      applyTheme(theme)
      localStorage.setItem(THEME_STORAGE_KEY, theme)
    } else {
      // Remove theme and return to the default indigo SaaS palette.
      document.documentElement.removeAttribute('data-theme')
      document.body.style.background = ''
      document.body.style.color = ''
      localStorage.removeItem(THEME_STORAGE_KEY)
      currentTheme.value = null
    }
  }

  function applyTheme(theme: ThemeName) {
    if (!theme) return
    currentTheme.value = theme
    document.documentElement.setAttribute('data-theme', theme)
    // Let CSS variables drive body styles via the theme system
    document.body.style.background = 'var(--bg)'
    document.body.style.color = 'var(--text)'
  }

  return { currentTheme, THEME_LIST, init, setTheme }
}
