import { afterEach, vi } from 'vitest'
import { enableAutoUnmount } from '@vue/test-utils'

enableAutoUnmount(afterEach)
vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
Object.defineProperty(window, 'matchMedia', { value: vi.fn(() => ({ matches: false, addListener: vi.fn(), removeListener: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() })) })
