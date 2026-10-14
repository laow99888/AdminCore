import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { ElButton } from 'element-plus'
import DataExportButton from '../src/components/common/DataExportButton.vue'
import { useAuthStore } from '../src/stores/auth'
import { useModuleStore } from '../src/stores/modules'
import { exportData } from '../src/api/dataExports'

vi.mock('../src/api/dataExports', () => ({ exportData: vi.fn(), exportErrorMessage: vi.fn().mockResolvedValue('可重试的导出错误') }))

function setup() {
  const auth = useAuthStore()
  auth.token = 'isolated-export-token'
  auth.user = { id: 'member', username: 'member', email: '', avatar: '', permissions: ['data_io:export', 'user:read'] }
  const modules = useModuleStore()
  modules.config = { contract_version: 1, preset: 'standard', modules: [{ key: 'data_io', title: '', enabled: true, dependencies: [], paths: [] }] }
  const wrapper = mount(DataExportButton, { props: { resource: 'users', filters: { search: 'applied' } }, global: { components: { ElButton } } })
  return { auth, modules, wrapper }
}

describe('批量导出下载与身份边界', () => {
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.stubGlobal('URL', class extends URL {
      static createObjectURL = vi.fn(() => 'blob:export-fixture')
      static revokeObjectURL = vi.fn()
    })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  })

  it('下载成功使用明确文件名并释放 Blob URL', async () => {
    vi.mocked(exportData).mockResolvedValue(new Blob(['fixture']))
    const { wrapper } = setup()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(exportData).toHaveBeenCalledWith('users', 'csv', { search: 'applied' }, expect.any(AbortSignal))
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledOnce()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:export-fixture')
    expect(wrapper.findAll('button').every(button => button.attributes('disabled') === undefined)).toBe(true)
  })

  it('列表未成功加载时禁用导出，加载完成恢复', async () => {
    const { wrapper } = setup()
    await wrapper.setProps({ loading: true })
    expect(wrapper.findAll('button').every(button => button.attributes('disabled') !== undefined)).toBe(true)
    await wrapper.get('button').trigger('click')
    expect(exportData).not.toHaveBeenCalled()
    await wrapper.setProps({ loading: false })
    expect(wrapper.get('button').attributes('disabled')).toBeUndefined()
  })

  it.each(['token', 'identity', 'permissions', 'modules', 'filters', 'loading', 'unmount'] as const)('%s 改变时取消请求，晚到成功结果不能下载', async kind => {
    let resolve!: (value: Blob) => void
    vi.mocked(exportData).mockReturnValue(new Promise(done => { resolve = done }))
    const { auth, modules, wrapper } = setup()
    await wrapper.get('button').trigger('click')
    const signal = vi.mocked(exportData).mock.calls[0]![3]!
    if (kind === 'token') auth.token = 'another-export-token'
    if (kind === 'identity') auth.user!.id = 'another-member'
    if (kind === 'permissions') auth.user!.permissions = ['user:read']
    if (kind === 'modules') modules.config!.modules[0]!.enabled = false
    if (kind === 'filters') await wrapper.setProps({ filters: { search: 'different' } })
    if (kind === 'loading') await wrapper.setProps({ loading: true })
    if (kind === 'unmount') wrapper.unmount()
    expect(signal.aborted).toBe(true)
    resolve(new Blob(['stale result']))
    await flushPromises()
    expect(URL.createObjectURL).not.toHaveBeenCalled()
    expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled()
  })

  it('请求失败显示可重试错误并解除按钮锁', async () => {
    vi.mocked(exportData).mockRejectedValue(new Error('fixture failed'))
    const { wrapper } = setup()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('可重试的导出错误')
    expect(wrapper.get('button').attributes('disabled')).toBeUndefined()
    vi.mocked(exportData).mockResolvedValue(new Blob(['retried']))
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledOnce()
  })
})
