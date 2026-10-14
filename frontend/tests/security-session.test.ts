import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { watch } from 'vue'
vi.mock('../src/api/auth', () => ({ default: { me: vi.fn(), login: vi.fn() } }))
import authApi from '../src/api/auth'
import { useAuthStore } from '../src/stores/auth'
const jwt = (sid: string) => `fixture.${btoa(JSON.stringify({ sid, user_id: 'u', session_version: 1 }))}.fixture`
const user = { id: 'u', username: 'member', email: '', avatar: '', permissions: [] }
const old = jwt('old'), next = jwt('new')

describe('双重证明后的当前会话替换', () => {
  beforeEach(() => { vi.resetAllMocks(); localStorage.clear(); localStorage.setItem('token', old); setActivePinia(createPinia()) })
  it('完整me增加权限字段仍属于同次登录，缓存监听不能取消导航', async () => {
    const auth = useAuthStore()
    vi.mocked(authApi.login).mockResolvedValue({ access: next, refresh: 'fixture', user })
    vi.mocked(authApi.me).mockResolvedValue({ ...user, permissions: ['*'], is_staff: true, is_superuser: true })
    const observations: boolean[] = []
    watch(() => JSON.stringify([auth.token, auth.user?.id, auth.user?.permissions, auth.user?.is_staff]), () => {
      observations.push(auth.preservingSecuritySession)
      if (!auth.preservingSecuritySession) auth.cancelPendingLogin()
    }, { flush: 'sync' })
    await auth.login('member', 'fixture')
    expect(auth.user?.permissions).toEqual(['*'])
    expect(observations.length).toBeGreaterThan(1)
    expect(observations.every(Boolean)).toBe(true)
    expect(auth.preservingSecuritySession).toBe(false)
  })
  it('login的第四参数原样传递单次captcha，仍只安装认证结果', async () => {
    const auth = useAuthStore(); vi.mocked(authApi.login).mockResolvedValue({ access: next, refresh: 'fixture', user }); vi.mocked(authApi.me).mockResolvedValue(user)
    const proof = { captcha_id: '00000000-0000-4000-8000-000000000001', captcha_code: 'ABCDE' }
    await auth.login('member', 'fixture', '123456', proof)
    expect(authApi.login).toHaveBeenCalledWith('member', 'fixture', '123456', proof)
    expect(localStorage.getItem('token')).toBe(next); expect(JSON.stringify({ ...localStorage })).not.toContain('ABCDE')
  })
  it('同步替换当前token并阻止旧个人资料响应覆盖新用户状态', async () => {
    const auth = useAuthStore(); auth.applyUser(user)
    let resolve!: (value: typeof user) => void
    vi.mocked(authApi.me).mockImplementation(() => new Promise(done => { resolve = done }))
    const pending = auth.fetchUser(true)
    const observations: boolean[] = []
    watch(() => auth.token, () => { observations.push(auth.preservingSecuritySession) }, { flush: 'sync' })
    expect(auth.replaceSecuritySession({ access: next, refresh: 'new-refresh', user: { ...user, totp_enabled: true } }, old)).toBe(true)
    resolve({ ...user, username: 'stale' }); await pending
    expect(auth.user?.username).toBe('member')
    expect(auth.user?.totp_enabled).toBe(true)
    expect(observations).toEqual([true])
    expect(auth.preservingSecuritySession).toBe(false)
    expect(localStorage.getItem('token')).toBe(next)
  })
  it('登出或另一会话登录后拒绝晚到安全修改结果', () => {
    const auth = useAuthStore(); auth.applyUser(user)
    localStorage.setItem('token', jwt('replacement'))
    expect(auth.replaceSecuritySession({ access: next, refresh: 'new-refresh', user }, old)).toBe(false)
    expect(localStorage.getItem('token')).toBe(jwt('replacement'))
    auth.clearSession()
    expect(auth.replaceSecuritySession({ access: next, refresh: 'new-refresh', user }, old)).toBe(false)
  })
  it('login页面卸载取消pending，旧响应不能新建JWT会话', async () => {
    const auth = useAuthStore()
    let resolve!: (data: { access: string; refresh: string; user: typeof user }) => void
    vi.mocked(authApi.login).mockImplementation(() => new Promise(done => { resolve = done }))
    const pending = auth.login('member', 'fixture')
    auth.cancelPendingLogin()
    resolve({ access: next, refresh: 'fixture', user })
    await expect(pending).rejects.toThrow('Login session changed')
    expect(localStorage.getItem('token')).toBe(old)
  })
})
