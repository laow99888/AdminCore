import { i18n } from './index'
import { uiMessages } from './uiMessages'

/** 仅由编译登记的页面注册静态文案；页面依赖随路由加载。 */
export function registerUiMessages(messages: Record<string, string>): void {
  Object.assign(uiMessages, messages)
}

/** 源文案与翻译固定映射；用户提交的内容不参与翻译。 */
export function uiText(source: string, values: Record<string, unknown> = {}): string {
  const message = i18n.global.locale.value === 'en-US' ? (uiMessages[source] || source) : source
  return message.replace(/\{(p\d+)\}/g, (_match, key: string) => String(values[key] ?? ''))
}
