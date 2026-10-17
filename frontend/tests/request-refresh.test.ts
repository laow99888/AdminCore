import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { tokensBelongToSameSession } from '../src/api/tokenRefresh'
import { ElMessage } from 'element-plus'
const mocks = vi.hoisted(() => ({ rejected: undefined as ((error: unknown) => Promise<unknown>) | undefined,
  fulfilled: undefined as ((response: { config: { url: string; _sessionToken: string }; data: unknown }) => unknown) | undefined,
  request: Object.assign(vi.fn(), { defaults: { baseURL: '/api/v1' }, interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } } }),
  post: vi.fn(), clear: vi.fn(), push: vi.fn(), refresh: vi.fn() }))
vi.mock('axios', () => ({ default: { create: () => mocks.request, post: mocks.post, isCancel: () => false } }))
vi.mock('../src/api/publicRequest', () => ({ default: { post: mocks.post } }))
vi.mock('../src/router', () => ({ default: { currentRoute: { value: { path: '/settings/sessions' } }, push: mocks.push } }))
vi.mock('../src/stores/auth', () => ({ useAuthStore: () => ({ clearSession: mocks.clear }) }))
vi.mock('../src/api/tokenRefresh', async importOriginal => ({ ...(await importOriginal<typeof import('../src/api/tokenRefresh')>()), refreshSessionTokens: mocks.refresh }))
vi.mock('element-plus', () => ({ ElMessage: { error: vi.fn() } }))
vi.mock('../src/i18n/uiText', () => ({ uiText: (text: string) => text }))

const jwt = (sid: string, marker: string) => `fixture.${btoa(JSON.stringify({ sid, user_id: 'u', session_version: 1, marker }))}.fixture`
const old = jwt('first', 'old'), fresh = jwt('first', 'fresh'), replacement = jwt('replacement', 'access')
describe('401 拦截器刷新与会话边界', () => {
  beforeEach(async () => {
    vi.resetModules(); vi.clearAllMocks(); localStorage.clear()
    localStorage.setItem('token', old)
    mocks.request.interceptors.response.use.mockImplementation((fulfilled, rejected) => { mocks.fulfilled = fulfilled; mocks.rejected = rejected })
    await import('../src/api/request')
    mocks.request.mockResolvedValue({ data: 'retried' })
  })
  afterEach(() => vi.unstubAllEnvs())
  const failure = (token = old) => ({ response: { status: 401 }, config: { url: '/auth/sessions/', headers: { Authorization: `Bearer ${token}` } } })
  it('刷新通过无JWT的独立公开传输发送，保留返回令牌兼容性', async () => {
    mocks.refresh.mockImplementation(async (_token, exchange) => {
      expect(await exchange('isolated-refresh')).toEqual({ access: fresh, refresh: 'rotated-refresh' })
      return { access: fresh, stale: false }
    })
    mocks.post.mockResolvedValue({ data: { data: { access: fresh, refresh: 'rotated-refresh' } } })
    await mocks.rejected!(failure())
    expect(mocks.post).toHaveBeenCalledWith('/auth/refresh/', { refresh: 'isolated-refresh' })
  })
  it.each([['en-US', 'en'], ['zh-CN', 'zh-Hans'], ['unsupported', 'zh-Hans']])('请求采用当前界面语言 %s', (language, expected) => {
    const handler = mocks.request.interceptors.request.use.mock.calls[0]![0]
    localStorage.setItem('language', language!)
    const config = handler({ headers: {} })
    expect(config.headers['Accept-Language']).toBe(expected)
    expect(config.headers.Authorization).toBe(`Bearer ${old}`)
  })
  it.each([400, 401, 429, 503, undefined])('登录%s错误由登录页反馈，不refresh、不清会话、不发重复全局message', async status => {
    const error = { config: { url: '/auth/login/' }, ...(status ? { response: { status } } : {}) }
    await expect(mocks.rejected!(error)).rejects.toBe(error)
    expect(mocks.refresh).not.toHaveBeenCalled(); expect(mocks.clear).not.toHaveBeenCalled(); expect(ElMessage.error).not.toHaveBeenCalled()
  })
  it('同标签并发401只刷新一次并使用新token重放', async () => {
    let resolve!: (result: { access: string; stale: boolean }) => void
    mocks.refresh.mockImplementation(() => new Promise(done => { resolve = done }))
    const first = mocks.rejected!(failure()), second = mocks.rejected!(failure())
    localStorage.setItem('token', fresh)
    resolve({ access: fresh, stale: false })
    await Promise.all([first, second])
    expect(mocks.refresh).toHaveBeenCalledTimes(1)
    expect(mocks.refresh.mock.calls[0]![0]).toBe(old)
    expect(mocks.request).toHaveBeenCalledTimes(2)
    expect(mocks.request.mock.calls[0]![0]).toMatchObject({ headers: { Authorization: `Bearer ${fresh}` }, _retried: true })
  })
  it('晚到刷新发现会话变化，不清新会话、不重放', async () => {
    mocks.refresh.mockResolvedValue({ access: null, stale: true })
    await expect(mocks.rejected!(failure())).rejects.toBeDefined()
    expect(mocks.clear).not.toHaveBeenCalled()
    expect(mocks.request).not.toHaveBeenCalled()
  })
  it('刷新失败且原会话仍在，清凭据并跳登录', async () => {
    mocks.refresh.mockResolvedValue({ access: null, stale: false })
    await expect(mocks.rejected!(failure())).rejects.toBeDefined()
    expect(mocks.clear).toHaveBeenCalledOnce()
    expect(mocks.push).toHaveBeenCalledWith('/login')
  })
  it('旧会话重试响应401时不清除新的登录', async () => {
    const error = failure()
    Object.assign(error.config, { _retried: true })
    localStorage.setItem('token', replacement)
    await expect(mocks.rejected!(error)).rejects.toBeDefined()
    expect(mocks.clear).not.toHaveBeenCalled()
  })
  it('旧refresh未完成时，新会话401启动自己的刷新且旧请求不跨会话重放', async () => {
    const resolve: ((result: { access: string; stale: boolean }) => void)[] = []
    mocks.refresh.mockImplementation(() => new Promise(done => { resolve.push(done) }))
    const first = mocks.rejected!(failure()).catch(error => error)
    localStorage.setItem('token', replacement)
    const second = mocks.rejected!(failure(replacement)).catch(error => error)
    expect(mocks.refresh).toHaveBeenCalledTimes(2)
    resolve[0]!({ access: fresh, stale: false })
    resolve[1]!({ access: replacement, stale: false })
    await Promise.all([first, second])
    expect(mocks.request).toHaveBeenCalledTimes(1)
    expect(mocks.request.mock.calls[0]![0]).toMatchObject({ _sessionToken: replacement })
    expect(mocks.clear).not.toHaveBeenCalled()
  })
  it('返回新会话access时，旧请求仍被拒绝', async () => {
    mocks.refresh.mockResolvedValue({ access: replacement, stale: false })
    localStorage.setItem('token', replacement)
    await expect(mocks.rejected!(failure())).rejects.toBeDefined()
    expect(mocks.request).not.toHaveBeenCalled()
  })
  it('重放发出前的新登录会被request interceptor再次阻断', () => {
    const handler = mocks.request.interceptors.request.use.mock.calls[0]![0]
    localStorage.setItem('token', replacement)
    expect(() => handler({ _retried: true, _sessionToken: old, headers: { Authorization: `Bearer ${fresh}` } })).toThrow('Session changed before retry')
    expect(tokensBelongToSameSession(old, fresh)).toBe(true)
  })
  it('旧refresh失败时，新登录401不清除新会话', async () => {
    let resolve!: (result: { access: null; stale: boolean }) => void
    mocks.refresh.mockImplementation(() => new Promise(done => { resolve = done }))
    const pending = mocks.rejected!(failure()).catch(error => error)
    localStorage.setItem('token', replacement)
    resolve({ access: null, stale: false })
    await pending
    expect(mocks.clear).not.toHaveBeenCalled()
  })
  it('Cookie模式的TOTP证明401不自动刷新或退出，允许用户重新填写证明', async () => {
    vi.stubEnv('VITE_AUTH_SESSION_TRANSPORT', 'cookie')
    const storage = await import('../src/auth/tokenStorage')
    storage.setSession({ access: old, session_transport: 'cookie' })
    const error = { response: { status: 401 }, config: { url: '/auth/totp/enable/',
      _sessionToken: old, _skipAuthRefresh: true, headers: { Authorization: `Bearer ${old}` } } }
    await expect(mocks.rejected!(error)).rejects.toBe(error)
    expect(mocks.refresh).not.toHaveBeenCalled(); expect(mocks.clear).not.toHaveBeenCalled()
    expect(storage.getAccessToken()).toBe(old)
    storage.discardMemorySession()
  })
  it('Cookie身份变化后丢弃迟到成功正文和错误提示，不把旧数据交给新页面', async () => {
    vi.stubEnv('VITE_AUTH_SESSION_TRANSPORT', 'cookie')
    const storage = await import('../src/auth/tokenStorage')
    storage.setSession({ access: replacement, session_transport: 'cookie' })
    expect(() => mocks.fulfilled!({ config: { url: '/users/', _sessionToken: old }, data: 'old-sensitive-data' })).toThrow('Session changed')
    const error = { response: { status: 403, data: { message: 'old-sensitive-error' } },
      config: { url: '/users/', _sessionToken: old } }
    await expect(mocks.rejected!(error)).rejects.toMatchObject({ __CANCEL__: true })
    expect(ElMessage.error).not.toHaveBeenCalled(); expect(mocks.clear).not.toHaveBeenCalled()
    storage.discardMemorySession()
  })
})
