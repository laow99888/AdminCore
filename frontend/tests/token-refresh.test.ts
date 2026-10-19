import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { refreshSessionTokens } from '../src/api/tokenRefresh'

const token = (sid: string, marker: string) => `fixture.${btoa(JSON.stringify({ sid, user_id: 'u', session_version: 1, marker }))}.fixture`
const seed = (sid = 'session', marker = 'old') => { const access = token(sid, marker); localStorage.setItem('token', access); localStorage.setItem('refreshToken', token(sid, `refresh-${marker}`)); return access }

describe('单次刷新轮换与跨标签页协调', () => {
  beforeEach(() => { localStorage.clear(); Object.defineProperty(navigator, 'locks', { configurable: true, value: undefined }) })
  afterEach(() => { Object.defineProperty(navigator, 'locks', { configurable: true, value: undefined }) })
  it('锁内读取最新 refresh，两个标签页只轮换一次', async () => {
    let queue = Promise.resolve<unknown>(undefined)
    const request = vi.fn((_name: string, run: () => Promise<unknown>) => { const next = queue.then(run); queue = next.catch(() => undefined); return next })
    Object.defineProperty(navigator, 'locks', { configurable: true, value: { request } })
    const access = seed(), newAccess = token('session', 'new'), newRefresh = token('session', 'refresh-new')
    const post = vi.fn().mockResolvedValue({ access: newAccess, refresh: newRefresh })
    const results = await Promise.all([refreshSessionTokens(access, post), refreshSessionTokens(access, post)])
    expect(post).toHaveBeenCalledTimes(1)
    expect(results).toEqual([{ access: newAccess, stale: false }, { access: newAccess, stale: false }])
    expect(localStorage.getItem('refreshToken')).toBe(newRefresh)
  })
  it('等待锁时重新登录，旧请求不会刷新或重放为新账户', async () => {
    let run!: () => Promise<unknown>
    Object.defineProperty(navigator, 'locks', { configurable: true, value: { request: vi.fn((_name, callback) => { run = callback; return new Promise(resolve => { setTimeout(async () => resolve(await run()), 0) }) }) } })
    const access = seed(), post = vi.fn()
    const pending = refreshSessionTokens(access, post)
    const replacement = seed('new-session')
    expect(await pending).toEqual({ access: null, stale: true })
    expect(localStorage.getItem('token')).toBe(replacement)
    expect(post).not.toHaveBeenCalled()
  })
  it.each(['logout', 'login'])('请求中途%s，晚到响应不能写回或清除新会话', async action => {
    const access = seed()
    let resolve!: (value: { access: string; refresh: string }) => void
    const pending = refreshSessionTokens(access, () => new Promise(done => { resolve = done }))
    const expected = action === 'logout' ? (localStorage.clear(), null) : seed('replacement')
    resolve({ access: token('session', 'new'), refresh: token('session', 'refresh-new') })
    expect(await pending).toEqual({ access: null, stale: true })
    expect(localStorage.getItem('token')).toBe(expected)
  })
  it('无跨标签锁时，重复轮换失败可复用其他标签已取得的新access', async () => {
    const access = seed(), newAccess = token('session', 'new'), newRefresh = token('session', 'refresh-new')
    const result = await refreshSessionTokens(access, async () => {
      localStorage.setItem('token', newAccess); localStorage.setItem('refreshToken', newRefresh)
      throw new Error('already rotated')
    })
    expect(result).toEqual({ access: newAccess, stale: false })
  })
  it('服务器拒绝且会话未变化，返回失败供调用方清理', async () => {
    const access = seed()
    expect(await refreshSessionTokens(access, async () => { throw new Error('expired') })).toEqual({ access: null, stale: false })
  })
  it.each([undefined, 429, 503])('临时刷新失败 %s 保留凭据以便重试，不重放旧请求', async status => {
    const access = seed(), refresh = localStorage.getItem('refreshToken')
    const result = await refreshSessionTokens(access, async () => { throw { isAxiosError: true, ...(status ? { response: { status } } : {}) } })
    expect(result).toEqual({ access: null, stale: false, retryable: true })
    expect(localStorage.getItem('token')).toBe(access)
    expect(localStorage.getItem('refreshToken')).toBe(refresh)
  })

})
