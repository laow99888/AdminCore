export const KEYBOARD_SHORTCUTS_KEY = 'admincore:keyboard-shortcuts'
export const KEYBOARD_HELP_EVENT = 'admincore:keyboard-help'

export const keyboardCommands = [
  { key: 'Alt + Shift + H', title: '返回首页' },
  { key: 'Alt + Shift + S', title: '账户设置' },
  { key: 'Alt + Shift + W', title: '关闭当前页签' },
  { key: 'Alt + Shift + ←', title: '上一个页签' },
  { key: 'Alt + Shift + →', title: '下一个页签' },
  { key: '?', title: '快捷键帮助' },
] as const

export interface ShortcutContext {
  enabled: boolean
  active: boolean
  path: string
  tabs: readonly { path: string }[]
  allowed: (path: string) => boolean
  navigate: (path: string) => unknown
  close: (path: string) => unknown
  help: () => unknown
}

/** Deliberately exclude editable controls and open overlays before interpreting keys. */
export function shortcutBlocked(event: KeyboardEvent, document: Document) {
  if (event.defaultPrevented || event.repeat || event.isComposing || event.keyCode === 229) return true
  const target = event.target
  if (target instanceof Element && target.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"], [role="combobox"], [role="spinbutton"]')) return true
  return Array.from(document.querySelectorAll<HTMLElement>(
    '[role="dialog"], [role="alertdialog"], [role="menu"], [role="listbox"], .el-popper, .context-menu, .el-overlay',
  )).some(element => element.getClientRects().length > 0 && document.defaultView?.getComputedStyle(element).visibility !== 'hidden')
}

export function handleKeyboardShortcut(event: KeyboardEvent, context: ShortcutContext, document: Document) {
  if (!context.enabled || !context.active || shortcutBlocked(event, document)) return false
  let action: (() => unknown) | undefined
  if (event.key === '?' && !event.altKey && !event.ctrlKey && !event.metaKey) action = context.help
  else if (event.altKey && event.shiftKey && !event.ctrlKey && !event.metaKey) {
    const key = event.key.toLowerCase()
    let target: string | undefined
    const index = context.tabs.findIndex(tab => tab.path === context.path)
    if (key === 'h') target = '/'
    if (key === 's') target = '/settings'
    if (key === 'arrowleft' && index > 0) target = context.tabs[index - 1]?.path
    if (key === 'arrowright' && index >= 0) target = context.tabs[index + 1]?.path
    if (target && target !== context.path && context.allowed(target)) action = () => context.navigate(target!)
    // NavigationStore.close uses the preceding tab; check that exact destination too.
    if (key === 'w' && context.path !== '/' && index >= 0 && context.allowed(context.path) &&
        context.allowed(context.tabs[index - 1]?.path || '/')) action = () => context.close(context.path)
  }
  if (!action) return false
  event.preventDefault()
  try { void Promise.resolve(action()).catch(() => {}) } catch { /* Router recovery handles failed navigation. */ }
  return true
}

/** One active owner per window; stale KeepAlive instances cannot remove the new owner. */
const owners = new WeakMap<Window, { stop: () => void }>()
export function installKeyboardShortcuts(window: Window, context: () => ShortcutContext, openHelp: () => void) {
  owners.get(window)?.stop()
  const keydown = (event: KeyboardEvent) => handleKeyboardShortcut(event, context(), window.document)
  const help = () => { if (context().active) openHelp() }
  window.addEventListener('keydown', keydown)
  window.addEventListener(KEYBOARD_HELP_EVENT, help)
  const owner = { stop() {
    window.removeEventListener('keydown', keydown)
    window.removeEventListener(KEYBOARD_HELP_EVENT, help)
    if (owners.get(window) === owner) owners.delete(window)
  } }
  owners.set(window, owner)
  return owner.stop
}

export function readKeyboardPreference(storage: Storage): { enabled: boolean; persistenceAvailable: boolean } {
  try { return { enabled: storage.getItem(KEYBOARD_SHORTCUTS_KEY) === 'true', persistenceAvailable: true } }
  catch { return { enabled: false, persistenceAvailable: false } }
}

export function writeKeyboardPreference(storage: Storage, enabled: boolean) {
  try { storage.setItem(KEYBOARD_SHORTCUTS_KEY, String(enabled)); return true } catch { return false }
}
