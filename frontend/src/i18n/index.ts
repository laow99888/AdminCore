import { createI18n } from 'vue-i18n'
import type { I18n } from 'vue-i18n'
import zhCN from './locales/zh-CN'
import enUS from './locales/en-US'

export function setupI18n(): I18n<any, any, any, string, false> {
  const i18n = createI18n({
    legacy: false,
    locale: localStorage.getItem('language') || 'zh-CN',
    fallbackLocale: 'zh-CN',
    messages: {
      'zh-CN': zhCN,
      'en-US': enUS,
    },
  })

  return i18n
}

export { useI18n } from 'vue-i18n'
export const i18n = setupI18n()
