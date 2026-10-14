import type { App } from 'vue'
import type { Router } from 'vue-router'

export type ErrorCategory = 'vue' | 'window' | 'promise' | 'navigation'
export interface SafeErrorEvent {
  readonly category: ErrorCategory
  readonly occurredAt: string
  readonly route: string
  readonly correlationId: string
}
export type ErrorSink = (event: SafeErrorEvent) => void | Promise<void>
const categories: readonly string[] = ['vue', 'window', 'promise', 'navigation']

/** Deliberately accepts no Error object: messages, stacks and user data never enter the sink. */
export function createErrorReporter() {
  let sink: ErrorSink | null = null
  let registered = new Set<string>()
  let inSink = false
  let windowStarted = Date.now()
  let count = 0
  let sequence = 0
  const recent = new Map<string, number>()
  return {
    registerRoutes(paths: readonly string[]) {
      // Only literal registered paths; never dynamic parameters, query strings or fragments.
      registered = new Set(paths.filter(path => /^(\/[a-zA-Z0-9_-]+)*\/?$/.test(path)))
    },
    configureSink(next: ErrorSink | null) { sink = typeof next === 'function' ? next : null },
    report(category: ErrorCategory, path?: string): void {
      if (!sink || inSink || !categories.includes(category)) return
      const now = Date.now()
      if (now - windowStarted >= 60_000 || now < windowStarted) {
        windowStarted = now
        count = 0
        recent.clear()
      }
      const route = path && registered.has(path) ? path : 'unregistered'
      const key = `${category}:${route}`
      const previous = recent.get(key)
      if (count >= 10 || (previous !== undefined && now - previous < 5_000)) return
      recent.set(key, now)
      count++
      sequence++
      let correlationId = `local-${sequence.toString(16)}`
      try { correlationId = crypto.randomUUID() } catch { /* Local fallback contains no identity. */ }
      const event: SafeErrorEvent = Object.freeze({ category, occurredAt: new Date(now).toISOString(), route, correlationId })
      inSink = true
      try {
        const result = sink(event)
        if (result && typeof result.then === 'function') {
          void Promise.resolve(result).catch(() => {})
        }
      } catch { /* A broken integration must not break the application. */ }
      finally { inSink = false }
    },
  }
}

export type ErrorReporter = ReturnType<typeof createErrorReporter>
export const errorReporter = createErrorReporter()

interface InstallOptions {
  app: App
  router: Router
  reporter?: ErrorReporter
  onNavigationError?: () => void
  onVueError?: () => void
}
const installations = new WeakMap<App, () => void>()

/** One installation per Vue app. Call the returned disposer before installing another integration. */
export function installErrorReporting({ app, router, reporter = errorReporter, onNavigationError, onVueError }: InstallOptions): () => void {
  const installed = installations.get(app)
  if (installed) return installed
  const currentPath = () => router.currentRoute.value.path
  const previous = app.config.errorHandler
  const recover = (callback?: () => void) => { try { callback?.() } catch { /* Recovery cannot cause a reporting loop. */ } }
  const vueHandler: NonNullable<App['config']['errorHandler']> = () => {
    reporter.report('vue', currentPath())
    recover(onVueError)
  }
  const windowHandler = () => reporter.report('window', currentPath())
  const rejectionHandler = () => reporter.report('promise', currentPath())
  app.config.errorHandler = vueHandler
  window.addEventListener('error', windowHandler)
  window.addEventListener('unhandledrejection', rejectionHandler)
  const removeRouterHandler = router.onError((_error, to) => {
    reporter.report('navigation', to.path)
    recover(onNavigationError)
  })
  const dispose = () => {
    window.removeEventListener('error', windowHandler)
    window.removeEventListener('unhandledrejection', rejectionHandler)
    removeRouterHandler()
    if (app.config.errorHandler === vueHandler) app.config.errorHandler = previous
    installations.delete(app)
  }
  installations.set(app, dispose)
  return dispose
}
