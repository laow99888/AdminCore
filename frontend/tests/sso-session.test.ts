import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
vi.mock('../src/api/auth', () => ({ default: { me: vi.fn(), avatar: vi.fn() } }))
vi.mock('../src/api/sso', () => ({ ssoApi: { complete: vi.fn() } }))
import authApi from '../src/api/auth'
import { ssoApi } from '../src/api/sso'
import { useAuthStore } from '../src/stores/auth'
const user = { id: 'sso-user', username: 'sso-user', email: '', avatar: '', permissions: [] }
const pair = { access: 'fixture-sso-access', refresh: 'fixture-sso-refresh', user }
describe('企业登录会话安装的并发边界', () => {
  beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); setActivePinia(createPinia()); vi.mocked(authApi.me).mockResolvedValue(user) })
  it('仅在完成接口成功后安装并读取当前权限', async () => {
    const auth = useAuthStore()
    vi.mocked(ssoApi.complete).mockResolvedValue(pair)
    await auth.loginSSO({ otp_code: '123456' })
    expect(auth.token).toBe(pair.access); expect(auth.user).toEqual(user)
    expect(authApi.me).toHaveBeenCalledOnce()
  })
  it('离开登录或切换会话后丢弃迟到结果', async () => {
    const auth = useAuthStore()
    let finish!: (value: typeof pair) => void
    vi.mocked(ssoApi.complete).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const waiting = auth.loginSSO({})
    await vi.waitFor(() => expect(ssoApi.complete).toHaveBeenCalled())
    auth.cancelPendingLogin()
    finish(pair)
    await expect(waiting).rejects.toThrow('Login session changed')
    expect(localStorage.getItem('token')).toBeNull(); expect(auth.user).toBeNull()
  })
  it('已有本地会话不允许隐式覆盖，失败或中止不安装令牌', async () => {
    localStorage.setItem('token', 'existing-session')
    const auth = useAuthStore()
    await expect(auth.loginSSO({})).rejects.toThrow('Already signed in')
    expect(ssoApi.complete).not.toHaveBeenCalled()
    expect(localStorage.getItem('token')).toBe('existing-session')
  })
})
