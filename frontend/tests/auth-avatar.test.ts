import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { flushPromises } from '@vue/test-utils'
vi.mock('../src/api/auth', () => ({ default: { avatar: vi.fn(), me: vi.fn() } }))
import authApi from '../src/api/auth'
import { useAuthStore, type CurrentUser } from '../src/stores/auth'
const user: CurrentUser = { id: 'u', username: 'user', email: '', avatar: 'https://external.example/unsafe', profile_version: 1, has_avatar: true, avatar_enabled: true }

describe('私有头像资源生命周期', () => {
  beforeEach(() => {
    vi.resetAllMocks(); localStorage.clear(); setActivePinia(createPinia())
    localStorage.setItem('token', 'isolated-avatar-fixture')
    vi.stubGlobal('URL', { createObjectURL: vi.fn(() => 'blob:fixture'), revokeObjectURL: vi.fn() })
    vi.mocked(authApi.avatar).mockResolvedValue(new Blob(['png'], { type: 'image/png' }))
  })
  it('同一版本只读取一次，替换和登出释放 URL', async () => {
    const auth = useAuthStore()
    auth.applyUser(user); await flushPromises()
    expect(auth.avatarUrl).toBe('blob:fixture')
    auth.applyUser({ ...user }); await flushPromises()
    expect(authApi.avatar).toHaveBeenCalledTimes(1)
    auth.applyUser({ ...user, profile_version: 2 }); await flushPromises()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:fixture')
    expect(authApi.avatar).toHaveBeenCalledTimes(2)
    auth.clearSession(); await nextTick()
    expect(auth.avatarUrl).toBe('')
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2)
  })
  it('登出取消读取，迟到的结果不能建立头像 URL', async () => {
    let resolve!: (blob: Blob) => void
    vi.mocked(authApi.avatar).mockImplementation(() => new Promise(done => { resolve = done }))
    const auth = useAuthStore(); auth.applyUser(user); await nextTick()
    const signal = vi.mocked(authApi.avatar).mock.calls[0]![0]
    auth.clearSession(); resolve(new Blob(['png'])); await flushPromises()
    expect(signal.aborted).toBe(true)
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })
  it('文件模块关闭或强制改密时不读取图片，外部旧头像不渲染', async () => {
    const auth = useAuthStore()
    auth.applyUser({ ...user, avatar_enabled: false }); await flushPromises()
    auth.applyUser({ ...user, must_change_password: true }); await flushPromises()
    expect(authApi.avatar).not.toHaveBeenCalled(); expect(auth.avatarUrl).toBe('')
  })
  it('读取及解码错误可重试，旧资源被回收', async () => {
    vi.mocked(authApi.avatar).mockRejectedValueOnce(new Error('failed'))
    const auth = useAuthStore(); auth.applyUser(user); await flushPromises()
    expect(auth.avatarError).toBe(true)
    await auth.loadAvatar(); expect(auth.avatarError).toBe(false)
    auth.avatarDecodeFailed(); expect(auth.avatarError).toBe(true)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:fixture')
    await auth.loadAvatar(); expect(auth.avatarUrl).toBe('blob:fixture')
  })
  it('资料保存后迟到的 me 响应不会覆盖新快照', async () => {
    let resolve!: (value: CurrentUser) => void
    vi.mocked(authApi.me).mockImplementation(() => new Promise(done => { resolve = done }))
    const auth = useAuthStore(); auth.token = 'fixture'
    const pending = auth.fetchUser(true)
    auth.applyUser({ ...user, profile_version: 3 })
    resolve({ ...user }); await pending
    expect(auth.user?.profile_version).toBe(3)
  })
})
