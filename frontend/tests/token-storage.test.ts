import { beforeEach, describe, expect, it } from 'vitest'
import {
  clearSession,
  getAccessToken,
  getRefreshToken,
  getSessionSnapshot,
  setAccessToken,
  setRefreshToken,
  setSession,
} from '../src/auth/tokenStorage'

describe('认证令牌存储适配器', () => {
  beforeEach(() => localStorage.clear())

  it('读取既有 localStorage 会话键，保持旧客户端兼容', () => {
    localStorage.setItem('token', 'access-fixture')
    localStorage.setItem('refreshToken', 'refresh-fixture')
    expect(getSessionSnapshot()).toEqual({ access: 'access-fixture', refresh: 'refresh-fixture' })
  })

  it('写入完整会话并允许单独轮换令牌', () => {
    setSession({ access: 'access-one', refresh: 'refresh-one' })
    expect(getAccessToken()).toBe('access-one')
    expect(getRefreshToken()).toBe('refresh-one')
    setAccessToken('access-two')
    setRefreshToken('refresh-two')
    expect(getSessionSnapshot()).toEqual({ access: 'access-two', refresh: 'refresh-two' })
  })

  it('清除会话时同时移除 access 和 refresh', () => {
    setSession({ access: 'access-one', refresh: 'refresh-one' })
    clearSession()
    expect(getSessionSnapshot()).toEqual({ access: null, refresh: null })
  })
})
