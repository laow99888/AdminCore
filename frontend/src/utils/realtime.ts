import { tokensBelongToSameSession } from '@/api/tokenRefresh'
import { apiLanguage } from '@/api/language'

export interface TopicSummary { total: number; changed_at: string | null }
export interface RealtimeTopics {
  notifications?: TopicSummary & { unread_count: number; read_at: string | null }
  approvals?: TopicSummary & { todo_count: number }
  tasks?: TopicSummary & { active_count: number; active: { id: string; status: 'pending' | 'running'; progress: number }[] }
}
export const REALTIME_EVENT = 'admincore:realtime-snapshot'

const count = (value: unknown): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= 0
const timestamp = (value: unknown) => value === null || (typeof value === 'string' && value.length <= 40 && /^\d{4}-\d\d-\d\dT/.test(value))
function summary(value: unknown): value is TopicSummary {
  return !!value && typeof value === 'object' && count((value as TopicSummary).total) && timestamp((value as TopicSummary).changed_at)
}

export function parseRealtimeSnapshot(raw: string): RealtimeTopics {
  const value = JSON.parse(raw) as { topics?: RealtimeTopics }
  const topics = value?.topics
  if (!topics || typeof topics !== 'object' || Array.isArray(topics) || Object.keys(topics).some(key => !['notifications', 'approvals', 'tasks'].includes(key))) throw new Error('Invalid realtime snapshot')
  const result: RealtimeTopics = {}
  if (topics.notifications) {
    const topic = topics.notifications
    if (!summary(topic) || !count(topic.unread_count) || topic.unread_count > topic.total || !timestamp(topic.read_at)) throw new Error('Invalid notifications snapshot')
    result.notifications = { total: topic.total, changed_at: topic.changed_at, unread_count: topic.unread_count, read_at: topic.read_at }
  }
  if (topics.approvals) {
    const topic = topics.approvals
    if (!summary(topic) || !count(topic.todo_count) || topic.todo_count > topic.total) throw new Error('Invalid approvals snapshot')
    result.approvals = { total: topic.total, changed_at: topic.changed_at, todo_count: topic.todo_count }
  }
  if (topics.tasks) {
    const topic = topics.tasks
    if (!summary(topic) || !count(topic.active_count) || topic.active_count > topic.total || !Array.isArray(topic.active) || topic.active.length > 20 ||
        topic.active.some(row => !row || typeof row.id !== 'string' || !/^[0-9a-f-]{36}$/i.test(row.id) || !['pending', 'running'].includes(row.status) || !count(row.progress) || row.progress > 100)) throw new Error('Invalid tasks snapshot')
    result.tasks = { total: topic.total, changed_at: topic.changed_at, active_count: topic.active_count,
      active: topic.active.map(row => ({ id: row.id, status: row.status, progress: row.progress })) }
  }
  return result
}

/** 有界 SSE 解码器：不执行事件内容，不把服务器事件名当作任意浏览器事件。 */
export function createSseDecoder(onEvent: (event: string, data: string) => void) {
  let pending = ''
  return (chunk: string) => {
    pending += chunk
    let boundary: number
    while ((boundary = pending.search(/\r?\n\r?\n/)) >= 0) {
      const separator = pending.slice(boundary).match(/^\r?\n\r?\n/)![0]
      const frame = pending.slice(0, boundary)
      pending = pending.slice(boundary + separator.length)
      if (frame.length > 65536) throw new Error('Oversized realtime frame')
      let event = 'message'
      const data: string[] = []
      for (const line of frame.split(/\r?\n/)) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''))
      }
      if (data.length && ['snapshot', 'access_revoked', 'unavailable'].includes(event)) onEvent(event, data.join('\n'))
    }
    if (pending.length > 65536) throw new Error('Oversized realtime frame')
  }
}

export function startRealtimeClient(options: { enabled: () => boolean; onSnapshot: (topics: RealtimeTopics) => void; onAuthExpired: () => Promise<unknown> }) {
  const owner = localStorage.getItem('token')
  let stopped = false
  let controller: AbortController | undefined
  let retryTimer: number | undefined
  let timeoutTimer: number | undefined
  let failures = 0
  const eligible = () => !stopped && options.enabled() && document.visibilityState !== 'hidden' && navigator.onLine !== false &&
    tokensBelongToSameSession(owner, localStorage.getItem('token'))
  const cancel = () => {
    window.clearTimeout(retryTimer); window.clearTimeout(timeoutTimer)
    controller?.abort()
    controller = undefined
  }
  const reconnect = (delay: number) => {
    window.clearTimeout(retryTimer)
    if (eligible()) retryTimer = window.setTimeout(() => { void connect() }, delay)
  }
  async function connect() {
    if (!eligible() || controller) return
    const request = new AbortController()
    controller = request
    const current = () => controller === request && !request.signal.aborted && eligible()
    let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
    let delay = Math.min(60000, 5000 * 2 ** failures)
    let authExpired = false
    const armTimeout = () => {
      window.clearTimeout(timeoutTimer)
      timeoutTimer = window.setTimeout(() => request.abort(), 12000)
    }
    try {
      armTimeout()
      // 长连接只发往当前源；凭据永不进入 URL、日志或浏览器事件。
      const response = await fetch('/api/v1/realtime/events/', { method: 'GET', credentials: 'omit', cache: 'no-store',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}`, Accept: 'text/event-stream', 'Accept-Language': apiLanguage() }, signal: request.signal })
      if (response.status === 401) authExpired = true
      if (response.status === 429 || response.status === 503) delay = 60000
      if (!response.ok || !response.headers.get('content-type')?.startsWith('text/event-stream') || !response.body) throw new Error('Realtime unavailable')
      const decoder = new TextDecoder('utf-8', { fatal: true })
      const decode = createSseDecoder((event, data) => {
        if (!current()) return
        if (event === 'access_revoked') { authExpired = true; request.abort(); throw new Error('Realtime authentication expired') }
        if (event === 'unavailable') { request.abort(); throw new Error('Realtime unavailable') }
        const topics = parseRealtimeSnapshot(data)
        if (current()) options.onSnapshot(topics)
      })
      reader = response.body.getReader()
      while (current()) {
        const { value, done } = await reader.read()
        if (done) { decode(decoder.decode()); break }
        armTimeout()
        decode(decoder.decode(value, { stream: true }))
      }
      failures = 0
      delay = 1000 + Math.floor(Math.random() * 500)
    } catch {
      failures = Math.min(4, failures + 1)
    } finally {
      await reader?.cancel().catch(() => undefined)
      if (controller === request) {
        window.clearTimeout(timeoutTimer)
        controller = undefined
        if (authExpired && eligible()) await options.onAuthExpired().catch(() => undefined)
        reconnect(delay)
      }
    }
  }
  const visibility = () => { if (eligible()) reconnect(0); else cancel() }
  document.addEventListener('visibilitychange', visibility)
  window.addEventListener('online', visibility)
  window.addEventListener('offline', visibility)
  void connect()
  return () => {
    stopped = true; cancel()
    document.removeEventListener('visibilitychange', visibility)
    window.removeEventListener('online', visibility)
    window.removeEventListener('offline', visibility)
  }
}
