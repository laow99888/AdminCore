import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, disposePinia, setActivePinia, type Pinia } from 'pinia'
vi.mock('../src/api/auth', () => ({ default: { me: vi.fn(), login: vi.fn(), logout: vi.fn() } }))
vi.mock('../src/api/publicRequest', () => ({ default: { get: vi.fn(), delete: vi.fn() } }))
vi.mock('../src/api/sso', () => ({ ssoApi: { complete: vi.fn() } }))
import authApi from '../src/api/auth'
import { ssoApi } from '../src/api/sso'
import publicRequest from '../src/api/publicRequest'
import { useAuthStore } from '../src/stores/auth'
import { clearSession, discardMemorySession, getAccessToken, setAccessToken, setSession } from '../src/auth/tokenStorage'

const token = (sid: string, marker = 1) => `fixture.${btoa(JSON.stringify({ sid, user_id: 'u', session_version: 1, marker }))}.fixture`
const user = { id: 'u', username: 'member', email: '', avatar: '', permissions: ['*'] }
const pair = (sid = 'one') => ({ access: token(sid), session_transport: 'cookie' as const, user })
let pinia: Pinia

describe('Cookie 模式认证状态与旧请求隔离', () => {
  beforeEach(() => {
    vi.stubEnv('VITE_AUTH_SESSION_TRANSPORT', 'cookie'); vi.resetAllMocks()
    localStorage.clear(); discardMemorySession(); pinia = createPinia(); setActivePinia(pinia)
    Object.defineProperty(navigator, 'locks', { configurable: true, value: { request: (_key: string, run: () => Promise<unknown>) => run() } })
    vi.mocked(authApi.login).mockResolvedValue(pair())
    vi.mocked(authApi.me).mockResolvedValue(user)
    vi.mocked(authApi.logout).mockResolvedValue(undefined)
    vi.mocked(ssoApi.complete).mockResolvedValue(pair())
    vi.mocked(publicRequest.get).mockResolvedValue({ data: { data: { csrf_token: 'proof' } } })
    vi.mocked(publicRequest.delete).mockResolvedValue({ status: 204 })
  })
  afterEach(() => { disposePinia(pinia); discardMemorySession(); vi.unstubAllEnvs() })

  it('无可读refresh也能登录和安装TOTP替换会话，正常轮换不清除用户', async () => {
    const auth = useAuthStore()
    await auth.login('member', 'fixture')
    expect(auth.isAuthenticated).toBe(true); expect(auth.refreshToken).toBe(''); expect(auth.user).toEqual(user)
    setAccessToken(token('one', 2))
    expect(auth.token).toBe(token('one', 2)); expect(auth.user).toEqual(user)
    expect(auth.replaceSecuritySession(pair('two'), token('one'))).toBe(true)
    expect(auth.token).toBe(token('two')); expect(auth.user).toEqual(user)
    expect(localStorage.getItem('token')).toBeNull(); expect(localStorage.getItem('refreshToken')).toBeNull()
  })

  it('退出或跨标签丢弃内存，用户和敏感数据缓存立即清空', async () => {
    const auth = useAuthStore(); await auth.login('member', 'fixture')
    discardMemorySession()
    expect(auth.token).toBe(''); expect(auth.user).toBeNull(); expect(auth.isAuthenticated).toBe(false)
  })

  it('SSO 无可读refresh也能安装会话；已有身份不能被隐式覆盖', async () => {
    const auth = useAuthStore()
    await auth.loginSSO({})
    expect(auth.isAuthenticated).toBe(true); expect(auth.user).toEqual(user)
    expect(localStorage.getItem('token')).toBeNull(); expect(localStorage.getItem('refreshToken')).toBeNull()
    await expect(auth.loginSSO({})).rejects.toThrow('Already signed in')
    expect(ssoApi.complete).toHaveBeenCalledOnce()
  })

  it('SSO 请求已发出后取消，迟到Cookie会话按sid撤销且不安装', async () => {
    const auth = useAuthStore()
    let finish!: (value: ReturnType<typeof pair>) => void
    vi.mocked(ssoApi.complete).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const waiting = auth.loginSSO({})
    await vi.waitFor(() => expect(ssoApi.complete).toHaveBeenCalledOnce())
    auth.cancelPendingLogin(); finish(pair())
    await expect(waiting).rejects.toThrow('Login session changed')
    expect(publicRequest.delete).toHaveBeenCalledWith('/auth/browser-session/', expect.objectContaining({ data: { session_id: 'one' } }))
    expect(getAccessToken()).toBeNull(); expect(auth.user).toBeNull()
  })

  it('用户请求等待期间另一个身份安装，旧me响应不能覆盖新状态', async () => {
    setSession(pair()); const auth = useAuthStore(); auth.applyUser(user)
    let finish!: (value: typeof user) => void
    vi.mocked(authApi.me).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const pending = auth.fetchUser(true)
    setSession(pair('replacement'))
    finish({ ...user, username: 'stale' }); await pending
    expect(auth.token).toBe(token('replacement')); expect(auth.user).toBeNull()
  })

  it('登录取消后撤销已签发Cookie并阻止下次自动恢复', async () => {
    const auth = useAuthStore()
    let finish!: (value: ReturnType<typeof pair>) => void
    vi.mocked(authApi.login).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const waiting = auth.login('member', 'fixture')
    auth.cancelPendingLogin(); finish(pair())
    await expect(waiting).rejects.toThrow('Login session changed')
    expect(publicRequest.delete).toHaveBeenCalledWith('/auth/browser-session/', expect.objectContaining({ data: { session_id: 'one' } }))
    expect(getAccessToken()).toBeNull(); expect(auth.user).toBeNull()
    expect(JSON.parse(localStorage.getItem('admincore.browser-session')!).state).toBe('signed_out')
  })

  it('退出失败仍清空本地；退出晚到不得清除替换后的身份', async () => {
    const auth = useAuthStore(); await auth.login('member', 'fixture')
    vi.mocked(authApi.logout).mockRejectedValue(new Error('network'))
    await expect(auth.logout()).rejects.toThrow('network')
    expect(getAccessToken()).toBeNull(); expect(auth.user).toBeNull()
    setSession(pair()); auth.applyUser(user)
    let finish!: () => void
    vi.mocked(authApi.logout).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const pending = auth.logout(); setSession(pair('replacement')); finish(); await pending
    expect(getAccessToken()).toBe(token('replacement'))
    clearSession()
  })
})
