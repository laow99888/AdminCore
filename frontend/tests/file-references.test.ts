import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus from 'element-plus'
import FileReferencesDialog from '../src/components/files/FileReferencesDialog.vue'
import { fileReferenceStatus, type FileReferenceStatus } from '../src/api/fileReferences'
import type { FileRow } from '../src/api'
import { useAuthStore } from '../src/stores/auth'
import { useModuleStore } from '../src/stores/modules'
import { useTenantStore } from '../src/stores/tenants'

vi.mock('../src/api/fileReferences', () => ({ fileReferenceStatus: vi.fn() }))
const Dialog = defineComponent({ props: ['modelValue'], template: '<section v-if="modelValue" role="dialog"><slot /><slot name="footer" /></section>' })
const file = { id: 'file', original_name: '合同.txt' } as FileRow
const wrappers: ReturnType<typeof mount>[] = []
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear(); setActivePinia(createPinia())
  vi.mocked(fileReferenceStatus).mockResolvedValue({ protected: true, lifecycle_version: 7 })
})
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()) })
async function setup(permissions = ['file:read']) {
  const auth = useAuthStore(), tenants = useTenantStore(), modules = useModuleStore()
  auth.token = 'session'; auth.user = { id: 'owner', username: 'owner', email: '', avatar: '', is_staff: false, permissions }
  modules.config = { contract_version: 1, preset: 'standard', modules: [{ key: 'files', title: '文件', enabled: true, dependencies: [], paths: ['/files'] }] }
  const wrapper = mount(FileReferencesDialog, { props: { file }, global: { plugins: [ElementPlus], stubs: { ElDialog: Dialog } } })
  wrappers.push(wrapper); await flushPromises()
  return { wrapper, auth, tenants, modules }
}
it('受保护提示说明删除限制和权限边界，关闭可达', async () => {
  const { wrapper } = await setup()
  expect(fileReferenceStatus).toHaveBeenCalledWith('file', expect.any(AbortSignal))
  expect(wrapper.text()).toContain('文件受引用保护'); expect(wrapper.text()).toContain('引用不授予附件访问权限')
  expect(wrapper.text()).toContain('不能移入回收站或彻底删除')
  await wrapper.get('button').trigger('click'); expect(wrapper.emitted('close')).toHaveLength(1)
})
it('无引用结果提示删除时重新检查；无文件不读取', async () => {
  vi.mocked(fileReferenceStatus).mockResolvedValue({ protected: false, lifecycle_version: 1 })
  const { wrapper } = await setup(); expect(wrapper.text()).toContain('删除时服务端会再次检查')
  await wrapper.setProps({ file: null }); expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  expect(fileReferenceStatus).toHaveBeenCalledTimes(1)
})
it('读取失败提供重试，恢复后展示状态', async () => {
  vi.mocked(fileReferenceStatus).mockRejectedValueOnce(new Error('offline'))
  const { wrapper } = await setup(); expect(wrapper.text()).toContain('无法检查引用，请重试')
  await wrapper.findAll('button').find(button => button.text() === '重试')!.trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('文件受引用保护')
})
it('没有读取权限不展示也不请求', async () => {
  const { wrapper } = await setup([])
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false); expect(fileReferenceStatus).not.toHaveBeenCalled()
})
it.each(['tenant', 'session', 'permission', 'module', 'password'] as const)('%s变更取消旧请求并关闭，不展示迟到状态', async change => {
  let resolve!: (value: FileReferenceStatus) => void
  vi.mocked(fileReferenceStatus).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const { wrapper, auth, tenants, modules } = await setup()
  expect(wrapper.text()).toContain('正在检查引用')
  const signal = vi.mocked(fileReferenceStatus).mock.calls[0]![1]!
  if (change === 'tenant') tenants.currentId = 'new-tenant'
  if (change === 'session') auth.token = 'new-session'
  if (change === 'permission') auth.user!.permissions = []
  if (change === 'module') modules.config!.modules[0]!.enabled = false
  if (change === 'password') auth.user!.must_change_password = true
  await flushPromises(); expect(signal.aborted).toBe(true); expect(wrapper.emitted('close')).toHaveLength(1)
  resolve({ protected: true, lifecycle_version: 7 }); await flushPromises()
  expect(wrapper.text()).not.toContain('文件受引用保护'); expect(fileReferenceStatus).toHaveBeenCalledTimes(1)
})
it('更换文件取消旧读取并忽略旧结果，卸载也取消请求', async () => {
  let resolve!: (value: FileReferenceStatus) => void
  vi.mocked(fileReferenceStatus).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const { wrapper } = await setup(); const oldSignal = vi.mocked(fileReferenceStatus).mock.calls[0]![1]!
  vi.mocked(fileReferenceStatus).mockResolvedValue({ protected: false, lifecycle_version: 1 })
  await wrapper.setProps({ file: { ...file, id: 'new' } }); await flushPromises()
  expect(oldSignal.aborted).toBe(true)
  resolve({ protected: true, lifecycle_version: 7 }); await flushPromises()
  expect(wrapper.text()).toContain('当前未发现受保护引用')
  const signal = vi.mocked(fileReferenceStatus).mock.calls[1]![1]!
  wrapper.unmount(); expect(signal.aborted).toBe(true)
})
