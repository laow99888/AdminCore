import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
vi.mock('../src/api/publicRequest', () => ({ default: { get: vi.fn(), post: vi.fn(), delete: vi.fn() } }))
import publicRequest from '../src/api/publicRequest'
import { initializeBrowserSession, refreshBrowserSession, logoutBrowserSession,
  startBrowserSessionSync, withBrowserSessionLock, discardCancelledBrowserLogin } from '../src/auth/browserSession'
import { announceBrowserSession, browserSessionMarker, clearSession, discardMemorySession, getAccessToken,
  getRefreshToken, setAccessToken, setRefreshToken, setSession } from '../src/auth/tokenStorage'
import { BROWSER_SESSION_MARKER, MEMORY_TOKEN_CHANGED } from '../src/auth/sessionTransport'

const token = (sid = 'session', marker = 'old') => `fixture.${btoa(JSON.stringify({ sid, user_id: 'u', session_version: 1, marker }))}.fixture`
const access = token()
const pair = (value = access) => ({ access: value, session_transport: 'cookie' as const })
const seed = () => setSession(pair())
const rejected = (status: number) => ({ response: { status } })
let dispose: (() => void) | undefined

function locks() {
  let queue = Promise.resolve<unknown>(undefined)
  const request = vi.fn((_name: string, run: () => Promise<unknown>) => {
    const next = queue.then(run); queue = next.catch(() => undefined); return next
  })
  Object.defineProperty(navigator, 'locks', { configurable: true, value: { request } })
  return request
}

describe('Cookie 浏览器会话的内存与跨标签协议', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_AUTH_SESSION_TRANSPORT', 'cookie')
    vi.resetAllMocks(); localStorage.clear(); discardMemorySession(); locks()
    vi.mocked(publicRequest.get).mockResolvedValue({ data: { data: { csrf_token: 'proof' } } })
    vi.mocked(publicRequest.post).mockResolvedValue({ data: { data: pair(token('session', 'new')) } })
    vi.mocked(publicRequest.delete).mockResolvedValue({ status: 204 })
  })
  afterEach(() => { dispose?.(); dispose = undefined; discardMemorySession(); vi.unstubAllEnvs() })

  it('access 只在内存，清除旧凭据且标记与事件不含任何令牌', () => {
    localStorage.setItem('token', 'legacy'); localStorage.setItem('refreshToken', 'legacy-refresh')
    const events: Event[] = [], listener = (event: Event) => events.push(event)
    window.addEventListener(MEMORY_TOKEN_CHANGED, listener)
    seed()
    expect(getAccessToken()).toBe(access); expect(getRefreshToken()).toBeNull()
    expect(localStorage.getItem('token')).toBeNull(); expect(localStorage.getItem('refreshToken')).toBeNull()
    expect(JSON.stringify({ ...localStorage })).not.toContain(access)
    expect(JSON.parse(browserSessionMarker()!)).toEqual({ state: 'active', epoch: expect.any(String) })
    expect(events).toHaveLength(1); expect('detail' in events[0]!).toBe(false)
    window.removeEventListener(MEMORY_TOKEN_CHANGED, listener)
    expect(() => setRefreshToken('forbidden')).toThrow()
    expect(() => setSession({ access, refresh: 'forbidden' })).toThrow()
    clearSession(); expect(getAccessToken()).toBeNull()
    expect(JSON.parse(browserSessionMarker()!).state).toBe('signed_out')
  })

  it('首次恢复只提交 Cookie 和 CSRF，内存重置后可再次恢复，不读取旧localStorage', async () => {
    localStorage.setItem('token', 'legacy'); localStorage.setItem('refreshToken', 'legacy-refresh')
    await initializeBrowserSession()
    expect(publicRequest.post).toHaveBeenCalledWith('/auth/browser-session/', {}, { headers: {
      'X-AdminCore-Session': 'cookie', 'X-CSRFToken': 'proof' } })
    expect(getAccessToken()).toBe(token('session', 'new')); expect(getRefreshToken()).toBeNull()
    discardMemorySession(); await initializeBrowserSession()
    expect(publicRequest.post).toHaveBeenCalledTimes(2)
    expect(JSON.stringify({ ...localStorage })).not.toContain('legacy')
  })

  it('signed_out 标记阻止取消登录后 Cookie 被悄悄恢复；服务端401按匿名处理', async () => {
    clearSession(); await initializeBrowserSession(); expect(publicRequest.get).not.toHaveBeenCalled()
    localStorage.clear(); vi.mocked(publicRequest.post).mockRejectedValue(rejected(401))
    await initializeBrowserSession(); expect(getAccessToken()).toBeNull()
  })

  it.each([403, 404, 429, 500])('恢复%s不静默回退旧凭据', async status => {
    vi.mocked(publicRequest.post).mockRejectedValue(rejected(status))
    await expect(initializeBrowserSession()).rejects.toEqual(rejected(status))
    expect(getAccessToken()).toBeNull()
  })

  it('刷新传入sid，两个并发401在锁后复用本标签的新access', async () => {
    seed()
    const results = await Promise.all([refreshBrowserSession(access), refreshBrowserSession(access)])
    expect(results).toEqual([{ access: token('session', 'new'), stale: false }, { access: token('session', 'new'), stale: false }])
    expect(publicRequest.post).toHaveBeenCalledOnce()
    expect(publicRequest.post).toHaveBeenCalledWith('/auth/browser-session/', { session_id: 'session' }, expect.any(Object))
  })

  it('等待锁时身份标记变化，不刷新或重放旧身份', async () => {
    seed()
    let finish!: () => void
    const first = withBrowserSessionLock(() => new Promise<void>(resolve => { finish = resolve }))
    await vi.waitFor(() => expect(finish).toBeTypeOf('function'))
    const waiting = refreshBrowserSession(access)
    announceBrowserSession('active'); discardMemorySession(); finish(); await first
    expect(await waiting).toEqual({ access: null, stale: true })
    expect(publicRequest.post).not.toHaveBeenCalled()
  })

  it.each(['clear', 'replacement'])('请求中途%s，迟到access不能安装', async action => {
    seed()
    let finish!: (value: unknown) => void
    vi.mocked(publicRequest.post).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const pending = refreshBrowserSession(access)
    await vi.waitFor(() => expect(publicRequest.post).toHaveBeenCalled())
    if (action === 'clear') clearSession()
    else setSession(pair(token('replacement')))
    finish({ data: { data: pair(token('session', 'late')) } })
    expect(await pending).toEqual({ access: null, stale: true })
    expect(getAccessToken()).toBe(action === 'clear' ? null : token('replacement'))
  })

  it.each([{ access }, { access, refresh: 'leaked', session_transport: 'cookie' }, pair(token('other'))])(
    '拒绝协商错误、可读refresh及不同身份的响应 %j', async response => {
      seed(); vi.mocked(publicRequest.post).mockResolvedValue({ data: { data: response } })
      expect(await refreshBrowserSession(access)).toEqual({ access: null, stale: false })
      expect(getAccessToken()).toBe(access)
    })

  it('退出无需Bearer，携带sid，取消登录撤销响应中的会话并标记退出', async () => {
    seed(); await logoutBrowserSession()
    expect(publicRequest.delete).toHaveBeenCalledWith('/auth/browser-session/', {
      headers: { 'X-AdminCore-Session': 'cookie', 'X-CSRFToken': 'proof' }, data: { session_id: 'session' } })
    await discardCancelledBrowserLogin(token('cancelled'))
    expect(publicRequest.delete).toHaveBeenLastCalledWith('/auth/browser-session/', expect.objectContaining({ data: { session_id: 'cancelled' } }))
    expect(getAccessToken()).toBeNull(); expect(JSON.parse(browserSessionMarker()!).state).toBe('signed_out')
  })

  it('其它标签更换身份时立即丢弃内存并通知页面；自身轮换不重载', () => {
    seed(); const onChange = vi.fn(); dispose = startBrowserSessionSync(onChange)
    setAccessToken(token('session', 'rotated')); window.dispatchEvent(new Event('focus'))
    expect(onChange).not.toHaveBeenCalled()
    localStorage.setItem(BROWSER_SESSION_MARKER, JSON.stringify({ state: 'active', epoch: 'other-tab' }))
    window.dispatchEvent(new StorageEvent('storage', { key: BROWSER_SESSION_MARKER }))
    expect(getAccessToken()).toBeNull(); expect(onChange).toHaveBeenCalledOnce()
    window.dispatchEvent(new Event('focus')); expect(onChange).toHaveBeenCalledOnce()
    dispose(); dispose = undefined
  })

  it('缺少Web Locks或API跨源时拒绝启动；旧模式不受影响', async () => {
    Object.defineProperty(navigator, 'locks', { configurable: true, value: undefined })
    await expect(initializeBrowserSession()).rejects.toThrow('Web Locks')
    expect(publicRequest.get).not.toHaveBeenCalled()
    vi.stubEnv('VITE_AUTH_SESSION_TRANSPORT', 'bearer')
    await expect(withBrowserSessionLock(async () => 'legacy')).resolves.toBe('legacy')
    await initializeBrowserSession(); expect(publicRequest.get).not.toHaveBeenCalled()
  })

  it('等待签发锁时其它标签签发身份，排队的旧登录操作不能覆盖它', async () => {
    let release!: () => void
    const first = withBrowserSessionLock(() => new Promise<void>(resolve => { release = resolve }))
    await vi.waitFor(() => expect(release).toBeTypeOf('function'))
    const run = vi.fn(async () => undefined)
    const second = withBrowserSessionLock(run)
    const result = expect(second).rejects.toThrow('changed while waiting')
    announceBrowserSession('active'); release(); await first; await result
    expect(run).not.toHaveBeenCalled()
  })
})

describe('Bearer 跨标签身份同步', () => {
  beforeEach(() => { vi.stubEnv('VITE_AUTH_SESSION_TRANSPORT', 'bearer'); localStorage.clear() })
  afterEach(() => { dispose?.(); dispose = undefined; localStorage.clear(); vi.unstubAllEnvs() })
  it('相同会话轮换同步令牌；换账号或退出通知页面重置', () => {
    localStorage.setItem('token', token('first'))
    const changed = vi.fn(); dispose = startBrowserSessionSync(changed)
    localStorage.setItem('token', token('first', 'rotated'))
    window.dispatchEvent(new StorageEvent('storage', { key: 'token' }))
    expect(changed).not.toHaveBeenCalled()
    localStorage.setItem('token', token('second'))
    window.dispatchEvent(new StorageEvent('storage', { key: 'token' }))
    expect(changed).toHaveBeenCalledOnce()
    localStorage.removeItem('token'); window.dispatchEvent(new Event('focus'))
    expect(changed).toHaveBeenCalledTimes(2)
  })
})
