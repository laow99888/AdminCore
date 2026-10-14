import { beforeEach, afterEach, describe, it, expect, vi } from 'vitest'
import { createSseDecoder, parseRealtimeSnapshot, startRealtimeClient } from '../src/utils/realtime'

const jwt = (sid: string) => `fixture.${btoa(JSON.stringify({ sid, user_id: 'user', session_version: 1 }))}.fixture`
const topics = { notifications: { total: 2, unread_count: 1, changed_at: null, read_at: null } }
const frame = `event: snapshot\ndata: ${JSON.stringify({ topics })}\n\n`
const flush = async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); await Promise.resolve() }

describe('有界实时快照', () => {
  it('跨块、CRLF、多行data和heartbeat，不接受任意浏览器事件', () => {
    const callback = vi.fn(), decode = createSseDecoder(callback)
    decode(': heartbeat\r\n\r\nevent: snap')
    decode('shot\r\ndata: {"topics":\r\ndata: {}}\r\n\r\nevent: click\ndata: private\n\n')
    expect(callback).toHaveBeenCalledOnce()
    expect(callback).toHaveBeenCalledWith('snapshot', '{"topics":\n{}}')
  })
  it('限制完整帧和未结束帧', () => {
    expect(() => createSseDecoder(vi.fn())('a'.repeat(65537))).toThrow('Oversized')
    expect(() => createSseDecoder(vi.fn())('data: ' + 'a'.repeat(65537) + '\n\n')).toThrow('Oversized')
  })
  it('安全白名单重建，未知topic/非法计数/任务行拒绝', () => {
    expect(parseRealtimeSnapshot(JSON.stringify({ topics }))).toEqual(topics)
    expect(parseRealtimeSnapshot(JSON.stringify({ topics: { notifications: { ...topics.notifications, password: 'private' } } }))).toEqual(topics)
    for (const value of [{ unknown: {} }, { notifications: { ...topics.notifications, unread_count: -1 } },
      { notifications: { ...topics.notifications, unread_count: 3 } }, { tasks: { total: 1, active_count: 1, changed_at: null, active: [{ id: 'bad', status: 'running', progress: 100 }] } }]) {
      expect(() => parseRealtimeSnapshot(JSON.stringify({ topics: value }))).toThrow()
    }
  })
})

describe('当前身份流与断线回退', () => {
  beforeEach(() => { vi.useFakeTimers(); localStorage.clear(); localStorage.setItem('token', jwt('one')); vi.stubGlobal('fetch', vi.fn()) })
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks() })
  it('只在header传JWT，分块恢复快照并关闭reader', async () => {
    const read = vi.fn().mockResolvedValueOnce({ value: new TextEncoder().encode(frame), done: false }).mockResolvedValueOnce({ done: true })
    const cancel = vi.fn().mockResolvedValue(undefined), onSnapshot = vi.fn()
    vi.mocked(fetch).mockResolvedValue({ ok: true, status: 200, headers: new Headers({ 'content-type': 'text/event-stream' }), body: { getReader: () => ({ read, cancel }) } } as unknown as Response)
    const stop = startRealtimeClient({ enabled: () => true, onSnapshot, onAuthExpired: vi.fn() })
    await flush()
    expect(fetch).toHaveBeenCalledWith('/api/v1/realtime/events/', expect.objectContaining({ headers: expect.objectContaining({ Authorization: `Bearer ${jwt('one')}` }), credentials: 'omit' }))
    expect(onSnapshot).toHaveBeenCalledWith(topics)
    stop(); await flush(); expect(cancel).toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(60000); expect(fetch).toHaveBeenCalledOnce()
  })
  it('另一身份登录后不应用迟到数据，也不继续重连', async () => {
    let resolve!: (response: Response) => void
    vi.mocked(fetch).mockImplementation(() => new Promise(done => { resolve = done }))
    const onSnapshot = vi.fn(), read = vi.fn()
    const stop = startRealtimeClient({ enabled: () => true, onSnapshot, onAuthExpired: vi.fn() })
    localStorage.setItem('token', jwt('replacement'))
    resolve({ ok: true, status: 200, headers: new Headers({ 'content-type': 'text/event-stream' }), body: { getReader: () => ({ read, cancel: vi.fn().mockResolvedValue(undefined) }) } } as unknown as Response)
    await flush(); await vi.advanceTimersByTimeAsync(60000)
    expect(onSnapshot).not.toHaveBeenCalled(); expect(read).not.toHaveBeenCalled(); expect(fetch).toHaveBeenCalledOnce(); stop()
  })
  it('容量不足一分钟回退，卸载后不再请求', async () => {
    vi.mocked(fetch).mockResolvedValue({ ok: false, status: 429 } as Response)
    const stop = startRealtimeClient({ enabled: () => true, onSnapshot: vi.fn(), onAuthExpired: vi.fn() })
    await flush(); await vi.advanceTimersByTimeAsync(59999); expect(fetch).toHaveBeenCalledOnce()
    await vi.advanceTimersByTimeAsync(1); expect(fetch).toHaveBeenCalledTimes(2)
    stop(); await vi.advanceTimersByTimeAsync(60000); expect(fetch).toHaveBeenCalledTimes(2)
  })
  it('401走现有会话复核，静默流有超时abort', async () => {
    vi.mocked(fetch).mockResolvedValueOnce({ ok: false, status: 401 } as Response)
    const reauth = vi.fn().mockResolvedValue(null)
    const stop = startRealtimeClient({ enabled: () => true, onSnapshot: vi.fn(), onAuthExpired: reauth })
    await flush(); expect(reauth).toHaveBeenCalledOnce(); stop()
    let signal!: AbortSignal
    vi.mocked(fetch).mockImplementation((_url, options) => { signal = options!.signal!; return new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new Error('aborted')))) })
    const stopSilent = startRealtimeClient({ enabled: () => true, onSnapshot: vi.fn(), onAuthExpired: vi.fn() })
    await vi.advanceTimersByTimeAsync(12000); expect(signal.aborted).toBe(true); stopSilent()
  })
})
