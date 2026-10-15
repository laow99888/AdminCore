import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { ElButton, ElMessage, ElMessageBox } from 'element-plus'
import DataImportButton from '../src/components/common/DataImportButton.vue'
import { useAuthStore } from '../src/stores/auth'
import { useModuleStore } from '../src/stores/modules'
import { importResource, importTemplate } from '../src/api/dataImports'

vi.mock('../src/api/dataImports', () => ({ importResource: vi.fn(), importTemplate: vi.fn() }))
vi.mock('../src/api/dataExports', () => ({ exportErrorMessage: vi.fn().mockResolvedValue('导入失败，请重试') }))

function setup() {
  const auth = useAuthStore(), modules = useModuleStore()
  auth.token = 'isolated-import-token'
  auth.user = { id: 'admin', username: 'admin', email: '', avatar: '', is_staff: true,
    permissions: ['data_io:import', 'role:update', 'post:update'] }
  modules.config = { contract_version: 1, preset: 'standard', modules: [
    { key: 'data_io', title: '', enabled: true, dependencies: [], paths: [] },
    { key: 'organization', title: '', enabled: true, dependencies: [], paths: [] },
  ] }
  const wrapper = mount(DataImportButton, { props: { resource: 'roles' }, global: { components: { ElButton } } })
  async function select(file = new File(['name\nnew-role\n'], 'roles.csv')) {
    Object.defineProperty(wrapper.get('input').element, 'files', { configurable: true, value: [file] })
    await wrapper.get('input').trigger('change')
  }
  return { wrapper, auth, modules, select }
}

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
  vi.clearAllMocks()
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL = vi.fn(() => 'blob:isolated-import-template')
    static revokeObjectURL = vi.fn()
  })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue(undefined as never)
  vi.spyOn(ElMessage, 'success').mockImplementation(() => ({ close: vi.fn() }))
  vi.mocked(importResource).mockResolvedValue({ id: 'task' })
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('资源导入确认和身份边界', () => {
  it('下载有限模板后释放URL', async () => {
    vi.mocked(importTemplate).mockResolvedValue(new Blob(['fixture']))
    const { wrapper } = setup()
    await wrapper.get('button').trigger('click'); await flushPromises()
    expect(importTemplate).toHaveBeenCalledWith('roles', expect.any(AbortSignal))
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledOnce()
    expect(URL.revokeObjectURL).toHaveBeenCalledOnce()
    wrapper.unmount()
  })

  it('无管理身份或资源写权限时隐藏入口', async () => {
    const { wrapper, auth } = setup()
    auth.user!.is_staff = false
    await flushPromises()
    expect(wrapper.find('button').exists()).toBe(false)
    auth.user!.is_staff = true; auth.user!.permissions = ['data_io:import']
    await flushPromises()
    expect(wrapper.find('button').exists()).toBe(false)
    wrapper.unmount()
  })

  it('确认期间锁定，重复文件事件只提交一次', async () => {
    let confirm!: () => void
    vi.mocked(ElMessageBox.confirm).mockReturnValue(new Promise(resolve => { confirm = () => resolve(undefined as never) }))
    const { wrapper, select } = setup()
    await select(); await select()
    expect(ElMessageBox.confirm).toHaveBeenCalledOnce()
    expect(importResource).not.toHaveBeenCalled()
    confirm(); await flushPromises()
    expect(importResource).toHaveBeenCalledOnce()
    expect(ElMessage.success).toHaveBeenCalledOnce()
    wrapper.unmount()
  })

  it.each(['identity', 'permissions', 'module', 'unmount'] as const)('确认期间%s改变不提交旧文件', async kind => {
    let confirm!: () => void
    vi.mocked(ElMessageBox.confirm).mockReturnValue(new Promise(resolve => { confirm = () => resolve(undefined as never) }))
    const { wrapper, select, auth, modules } = setup()
    await select()
    if (kind === 'identity') auth.user!.id = 'another'
    if (kind === 'permissions') auth.user!.permissions = []
    if (kind === 'module') modules.config!.modules[0]!.enabled = false
    if (kind === 'unmount') wrapper.unmount()
    confirm(); await flushPromises()
    expect(importResource).not.toHaveBeenCalled()
    if (kind !== 'unmount') wrapper.unmount()
  })

  it.each(['empty.csv', 'file.exe'])('拒绝无效文件%s', async name => {
    const { wrapper, select } = setup()
    await select(new File([], name)); await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('10 MiB')
    expect(ElMessageBox.confirm).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('取消确认不发请求且解除按钮锁', async () => {
    vi.mocked(ElMessageBox.confirm).mockRejectedValue('cancel')
    const { wrapper, select } = setup()
    await select(); await flushPromises()
    expect(importResource).not.toHaveBeenCalled()
    expect(wrapper.get('button').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('已提交后退出页面取消等待且不显示迟到成功', async () => {
    let done!: (value: { id: string }) => void
    vi.mocked(importResource).mockReturnValue(new Promise(resolve => { done = resolve }))
    const { wrapper, select } = setup()
    await select(); await flushPromises()
    const signal = vi.mocked(importResource).mock.calls[0]![2]!
    wrapper.unmount()
    expect(signal.aborted).toBe(true)
    done({ id: 'task' }); await flushPromises()
    expect(ElMessage.success).not.toHaveBeenCalled()
  })
})
