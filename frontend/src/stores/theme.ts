import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { createThemePalette, normalizeThemeColor, PRIMARY_STEPS } from '@/utils/themeColors'

export const THEME_COLOR_KEY = 'admincore:theme-color'
const customProperties = [...PRIMARY_STEPS.map(step => `--color-primary-${step}`),
  '--el-color-primary', '--el-color-primary-light-3', '--el-color-primary-light-5',
  '--el-color-primary-light-7', '--el-color-primary-light-8', '--el-color-primary-light-9',
  '--el-color-primary-dark-2', '--admincore-primary-on-color', '--admincore-primary-subtle',
  '--admincore-primary-rgb', '--color-primary-text']

export const useThemeStore = defineStore('theme', () => {
  const isDark = ref(false)
  const primaryColor = ref<string | null>(null)
  const persistenceAvailable = ref(true)
  const failedPreferences = new Set<string>()

  function applyTheme() {
    if (typeof document === 'undefined') return
    const root = document.documentElement
    root.classList.toggle('dark', isDark.value)
    if (!primaryColor.value) {
      for (const property of customProperties) root.style.removeProperty(property)
      root.removeAttribute('data-custom-theme-color')
      return
    }
    const result = createThemePalette(primaryColor.value, isDark.value)
    for (const step of PRIMARY_STEPS) root.style.setProperty(`--color-primary-${step}`, result.palette[step]!)
    const overrides: Record<string, string> = {
      '--el-color-primary': result.primary,
      '--color-primary-text': result.primary,
      '--el-color-primary-light-3': result.hover,
      '--el-color-primary-light-5': isDark.value ? result.palette[400]! : result.palette[300]!,
      '--el-color-primary-light-7': isDark.value ? result.palette[800]! : result.palette[200]!,
      '--el-color-primary-light-8': isDark.value ? result.palette[900]! : result.palette[100]!,
      '--el-color-primary-light-9': result.subtle,
      '--el-color-primary-dark-2': result.active,
      '--admincore-primary-on-color': result.onColor,
      '--admincore-primary-subtle': result.subtle,
      '--admincore-primary-rgb': [1, 3, 5].map(offset => parseInt(result.primary.slice(offset, offset + 2), 16)).join(', '),
    }
    for (const [property, value] of Object.entries(overrides)) root.style.setProperty(property, value)
    root.setAttribute('data-custom-theme-color', 'true')
  }

  function initTheme() {
    const read = (key: string) => {
      try { const value = localStorage.getItem(key); failedPreferences.delete(key); return value }
      catch { failedPreferences.add(key); return null }
    }
    const savedTheme = read('theme')
    primaryColor.value = normalizeThemeColor(read(THEME_COLOR_KEY))
    persistenceAvailable.value = failedPreferences.size === 0
    let systemDark = false
    if (savedTheme !== 'light' && savedTheme !== 'dark') {
      try { systemDark = typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia('(prefers-color-scheme: dark)').matches }
      catch { /* Without an available media query, the safe default is light. */ }
    }
    isDark.value = savedTheme === 'dark' || (savedTheme !== 'light' && systemDark)
    applyTheme()
  }

  function persist(key: string, value: string | null) {
    try {
      if (value === null) localStorage.removeItem(key)
      else localStorage.setItem(key, value)
      failedPreferences.delete(key)
    } catch { failedPreferences.add(key) }
    persistenceAvailable.value = failedPreferences.size === 0
  }

  function toggleTheme() {
    isDark.value = !isDark.value
    persist('theme', isDark.value ? 'dark' : 'light')
  }

  function setPrimaryColor(value: unknown): boolean {
    const normalized = normalizeThemeColor(value)
    if (!normalized) return false
    primaryColor.value = normalized
    persist(THEME_COLOR_KEY, normalized)
    return true
  }

  function resetPrimaryColor() {
    primaryColor.value = null
    persist(THEME_COLOR_KEY, null)
  }

  // Pinia owns and disposes this watcher. No global DOM listeners are installed.
  watch([isDark, primaryColor], applyTheme, { flush: 'sync' })
  initTheme()

  return { isDark, primaryColor, persistenceAvailable, initTheme, toggleTheme, setPrimaryColor, resetPrimaryColor }
})
