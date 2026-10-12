import { i18n } from './index'
import { uiMessages } from './uiMessages'

/** 源文案与翻译固定映射；用户提交的内容不参与翻译。 */
export function uiText(source: string, values: Record<string, unknown> = {}): string {
  const message = i18n.global.locale.value === 'en-US' ? (uiMessages[source] || source) : source
  return message.replace(/\{(p\d+)\}/g, (_match, key: string) => String(values[key] ?? ''))
}
