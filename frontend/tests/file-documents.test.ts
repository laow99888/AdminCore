import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus, { ElSelect } from 'element-plus'
import FileVersionsDialog from '../src/components/files/FileVersionsDialog.vue'
import FileCapacityPanel from '../src/components/files/FileCapacityPanel.vue'
import { fileDocumentsApi, type FileHistory } from '../src/api/fileDocuments'
import { filesApi, downloadFile, usersApi, type FileRow } from '../src/api'
import { useAuthStore } from '../src/stores/auth'
import { useModuleStore } from '../src/stores/modules'
import { useTenantStore } from '../src/stores/tenants'
vi.mock('../src/api/fileDocuments', async importOriginal => ({ ...await importOriginal<object>(), fileDocumentsApi: { history: vi.fn(), append: vi.fn(), capacity: vi.fn(), saveCapacity: vi.fn() } }))
vi.mock('../src/api', () => ({ filesApi: { upload: vi.fn(), downloadUrl: (id: string) => `/files/${id}/download/` }, downloadFile: vi.fn(), usersApi: { list: vi.fn() } }))
const Dialog = defineComponent({ props: ['modelValue'], template: '<section v-if="modelValue" role="dialog"><slot /><slot name="footer" /></section>' })
const wrappers: ReturnType<typeof mount>[] = []
const file = { id: 'anchor', original_name: '合同.txt' } as FileRow
const revision = { number: 1, file_id: 'old', original_name: '旧合同.txt', size: 7, created_at: '2026-10-18T00:00:00Z', restored_from: null }
const history: FileHistory = { version: 2, current_file: 'new', items: [{ ...revision, number: 2, file_id: 'new', original_name: '新合同.txt' }, revision], has_more: false }
const capacity = { used_bytes: 12, limit_bytes: 1048576, remaining_bytes: 1048564, version: 4 }
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear(); setActivePinia(createPinia())
  vi.mocked(fileDocumentsApi.history).mockResolvedValue(structuredClone(history))
  vi.mocked(fileDocumentsApi.append).mockResolvedValue({ ...history, version: 3 })
  vi.mocked(fileDocumentsApi.capacity).mockResolvedValue({ ...capacity })
  vi.mocked(fileDocumentsApi.saveCapacity).mockResolvedValue({ ...capacity, limit_bytes: 2097152, version: 5 })
  vi.mocked(filesApi.upload).mockResolvedValue({ data: { data: { id: 'uploaded' } } } as Awaited<ReturnType<typeof filesApi.upload>>)
})
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()) })
function token(sid = 'session', session_version = 1, jti = 'initial') { return `header.${btoa(JSON.stringify({ sid, user_id: 'owner', session_version, jti }))}.signature` }
async function setup(kind: 'versions' | 'capacity' = 'versions', permissions = ['file:read', 'file:upload', 'file:download'], staff = false, access = 'session') {
  const auth = useAuthStore(), tenants = useTenantStore(), modules = useModuleStore()
  auth.token = access; auth.user = { id: 'owner', username: 'owner', email: '', avatar: '', is_staff: staff, permissions }
  modules.config = { contract_version: 1, preset: 'standard', modules: ['files'].map(key => ({ key, title: key, enabled: true, dependencies: [], paths: [`/${key}`] })) }
  const wrapper = kind === 'versions'
    ? mount(FileVersionsDialog, { props: { file }, global: { plugins: [ElementPlus], stubs: { ElDialog: Dialog } } })
    : mount(FileCapacityPanel, { props: { refreshKey: 0 }, global: { plugins: [ElementPlus], stubs: { ElDialog: Dialog } } })
  wrappers.push(wrapper); await flushPromises(); return { wrapper, auth, tenants, modules }
}
function button(wrapper: ReturnType<typeof mount>, text: string) { return wrapper.findAll('button').find(item => item.text() === text)! }
async function choose(wrapper: ReturnType<typeof mount>) {
  const input = wrapper.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['version'], '合同2.txt')] })
  await input.trigger('change')
}
it('历史仅显示授权修订，下载使用认证入口，回退追加修订', async () => {
  const { wrapper } = await setup()
  expect(wrapper.text()).toContain('原文件和业务引用保持不变')
  expect(wrapper.text()).toContain('当前版本')
  await button(wrapper, '下载').trigger('click'); await flushPromises()
  expect(downloadFile).toHaveBeenCalledWith('/files/new/download/', '新合同.txt')
  const restores = wrapper.findAll('button').filter(item => item.text() === '设为当前版本')
  expect(restores[0]!.attributes('disabled')).toBeDefined()
  await restores[1]!.trigger('click'); await flushPromises()
  expect(fileDocumentsApi.append).toHaveBeenCalledWith('anchor', { version: 2, restore_number: 1 })
  expect(wrapper.emitted('updated')).toHaveLength(1)
})
it('上传成功而登记失败保留候选，重试不重复上传', async () => {
  vi.mocked(fileDocumentsApi.append).mockRejectedValueOnce(new Error('offline'))
  const { wrapper } = await setup(); await choose(wrapper)
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(wrapper.text()).toContain('尚未加入版本历史'); expect(wrapper.text()).toContain('版本操作失败')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(filesApi.upload).toHaveBeenCalledTimes(1)
  expect(fileDocumentsApi.append).toHaveBeenLastCalledWith('anchor', { version: 2, file_id: 'uploaded' })
  expect(wrapper.text()).not.toContain('尚未加入版本历史')
})
it('同一会话刷新令牌保留已上传候选和版本弹窗，重试不重复上传', async () => {
  vi.mocked(fileDocumentsApi.append).mockRejectedValueOnce(new Error('offline'))
  const { wrapper, auth } = await setup('versions', undefined, false, token()); await choose(wrapper)
  await wrapper.get('form').trigger('submit'); await flushPromises()
  auth.token = token('session', 1, 'rotated'); await flushPromises()
  expect(wrapper.emitted('close')).toBeUndefined()
  expect(wrapper.text()).toContain('尚未加入版本历史')
  expect(fileDocumentsApi.history).toHaveBeenCalledTimes(1)
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(filesApi.upload).toHaveBeenCalledTimes(1)
  expect(fileDocumentsApi.append).toHaveBeenLastCalledWith('anchor', { version: 2, file_id: 'uploaded' })
})
it.each(['sid', 'version'] as const)('%s变更仍关闭版本弹窗并丢弃旧会话上传结果', async change => {
  let resolve!: (value: Awaited<ReturnType<typeof filesApi.upload>>) => void
  vi.mocked(filesApi.upload).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const { wrapper, auth } = await setup('versions', undefined, false, token()); await choose(wrapper)
  await wrapper.get('form').trigger('submit')
  auth.token = change === 'sid' ? token('other') : token('session', 2)
  await flushPromises(); resolve({ data: { data: { id: 'late' } } } as Awaited<ReturnType<typeof filesApi.upload>>); await flushPromises()
  expect(wrapper.emitted('close')).toHaveLength(1)
  expect(fileDocumentsApi.append).not.toHaveBeenCalled()
  expect(wrapper.text()).not.toContain('新合同.txt')
})
it('409重新读取后用新版本重试，不自动覆盖并发修改', async () => {
  const { wrapper } = await setup(); await choose(wrapper)
  vi.mocked(fileDocumentsApi.append).mockRejectedValueOnce({ response: { status: 409 } })
  vi.mocked(fileDocumentsApi.history).mockResolvedValueOnce({ ...history, version: 9 })
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(wrapper.text()).toContain('请确认后重试'); expect(fileDocumentsApi.append).toHaveBeenCalledTimes(1)
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(fileDocumentsApi.append).toHaveBeenLastCalledWith('anchor', { version: 9, file_id: 'uploaded' })
  expect(filesApi.upload).toHaveBeenCalledTimes(1)
})
it('上传容量409保留文件选择，不能误判为文档版本冲突', async () => {
  vi.mocked(filesApi.upload).mockRejectedValueOnce({ response: { status: 409 } })
  const { wrapper } = await setup(); await choose(wrapper)
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(wrapper.text()).toContain('附件上传失败，请检查容量或上传限制')
  expect(wrapper.text()).not.toContain('版本已变更')
  expect(fileDocumentsApi.history).toHaveBeenCalledTimes(1)
  expect(fileDocumentsApi.append).not.toHaveBeenCalled()
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(filesApi.upload).toHaveBeenCalledTimes(2)
  expect(fileDocumentsApi.append).toHaveBeenCalledWith('anchor', { version: 2, file_id: 'uploaded' })
})
it('读取失败可重试；只读用户看不到写入和下载入口', async () => {
  vi.mocked(fileDocumentsApi.history).mockRejectedValueOnce(new Error('offline'))
  const { wrapper } = await setup('versions', ['file:read'])
  expect(wrapper.text()).toContain('无法读取版本'); await button(wrapper, '重试').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('新合同.txt'); expect(wrapper.find('form').exists()).toBe(false)
  expect(button(wrapper, '下载')).toBeUndefined()
})
it('无权限不读，未建立历史可上传；分页请求只读下一页', async () => {
  const { wrapper } = await setup('versions', [])
  expect(fileDocumentsApi.history).not.toHaveBeenCalled(); expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  vi.mocked(fileDocumentsApi.history).mockResolvedValueOnce({ version: 0, current_file: 'anchor', items: [], has_more: false })
  const other = await setup(); expect(other.wrapper.text()).toContain('尚无版本历史')
  vi.mocked(fileDocumentsApi.history).mockResolvedValueOnce({ ...history, has_more: true })
  await other.wrapper.setProps({ file: { ...file, id: 'second' } }); await flushPromises()
  await button(other.wrapper, '下一页').trigger('click'); await flushPromises()
  expect(fileDocumentsApi.history).toHaveBeenLastCalledWith('second', 2, expect.any(AbortSignal))
})
it.each(['tenant', 'session', 'permission', 'password', 'module'] as const)('%s变化清空历史并拒绝迟到上传后的版本登记', async change => {
  let resolve!: (value: Awaited<ReturnType<typeof filesApi.upload>>) => void
  vi.mocked(filesApi.upload).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const { wrapper, auth, tenants, modules } = await setup(); await choose(wrapper); await wrapper.get('form').trigger('submit')
  if (change === 'tenant') tenants.currentId = 'other'
  if (change === 'session') auth.token = 'other'
  if (change === 'permission') auth.user!.permissions = ['file:read']
  if (change === 'password') auth.user!.must_change_password = true
  if (change === 'module') modules.config!.modules[0]!.enabled = false
  await flushPromises(); resolve({ data: { data: { id: 'late' } } } as Awaited<ReturnType<typeof filesApi.upload>>); await flushPromises()
  expect(fileDocumentsApi.append).not.toHaveBeenCalled(); expect(wrapper.emitted('close')).toHaveLength(1)
  expect(wrapper.text()).not.toContain('新合同.txt')
})
it('自己的逻辑容量显示精确统计，普通用户不能配置', async () => {
  const { wrapper } = await setup('capacity')
  expect(wrapper.text()).toContain('已使用 12 B'); expect(wrapper.text()).toContain('上限 1.00 MiB')
  expect(wrapper.text()).toContain('历史版本和回收站继续占用'); expect(button(wrapper, '容量管理')).toBeUndefined()
  await wrapper.setProps({ refreshKey: 1 }); await flushPromises(); expect(fileDocumentsApi.capacity).toHaveBeenCalledTimes(2)
})
it('管理员设置MiB换算字节，并携带版本；保存失败保留输入', async () => {
  const { wrapper } = await setup('capacity', ['file:read', 'file:upload'], true)
  await button(wrapper, '容量管理').trigger('click'); await flushPromises()
  await wrapper.get('input[role="spinbutton"]').setValue('2')
  vi.mocked(fileDocumentsApi.saveCapacity).mockRejectedValueOnce(new Error('offline'))
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(wrapper.text()).toContain('输入已保留'); expect(wrapper.get('input[role="spinbutton"]').element).toHaveProperty('value', '2')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(fileDocumentsApi.saveCapacity).toHaveBeenLastCalledWith('owner', 2097152, 4)
  expect(wrapper.text()).toContain('上限 2.00 MiB')
})
it('核心用户模块无需可选模块描述，管理员可搜索并保存其他用户容量', async () => {
  const otherUser = { id: 'other', username: 'other-user', version: 1, email: '', first_name: '', last_name: '', is_active: true, created_at: '' }
  vi.mocked(usersApi.list).mockResolvedValue({ items: [otherUser], pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 } })
  const { wrapper, modules } = await setup('capacity', ['file:read', 'file:upload', 'user:read'], true)
  expect(modules.config!.modules.some(row => row.key === 'users')).toBe(false)
  await button(wrapper, '容量管理').trigger('click'); await flushPromises()
  const picker = wrapper.getComponent(ElSelect)
  await picker.props('remoteMethod')!('other'); await flushPromises()
  expect(usersApi.list).toHaveBeenCalledWith({ search: 'other', is_active: true, page: 1, page_size: 20 })
  picker.vm.$emit('update:modelValue', otherUser.id); picker.vm.$emit('change', otherUser.id); await flushPromises()
  expect(fileDocumentsApi.capacity).toHaveBeenLastCalledWith(otherUser.id, expect.any(AbortSignal))
  await wrapper.get('input[role="spinbutton"]').setValue('2')
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(fileDocumentsApi.saveCapacity).toHaveBeenCalledWith(otherUser.id, 2097152, 4)
  expect(wrapper.text()).toContain('上限 1.00 MiB')
})
it('没有用户读取权限的管理员只能配置本人容量', async () => {
  const { wrapper } = await setup('capacity', ['file:read', 'file:upload'], true)
  await button(wrapper, '容量管理').trigger('click'); await flushPromises()
  expect(wrapper.findComponent(ElSelect).exists()).toBe(false)
  expect(usersApi.list).not.toHaveBeenCalled()
})
it('容量冲突必须重读再编辑，不能使用旧版本继续保存', async () => {
  const { wrapper } = await setup('capacity', ['file:read', 'file:upload'], true)
  await button(wrapper, '容量管理').trigger('click'); await flushPromises()
  await wrapper.get('input[role="spinbutton"]').setValue('2')
  vi.mocked(fileDocumentsApi.saveCapacity).mockRejectedValueOnce({ response: { status: 409 } })
  await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(wrapper.text()).toContain('重新读取后再编辑'); await wrapper.get('form').trigger('submit'); await flushPromises()
  expect(fileDocumentsApi.saveCapacity).toHaveBeenCalledTimes(1)
  await button(wrapper, '重试').trigger('click'); await flushPromises(); expect(wrapper.text()).not.toContain('重新读取后再编辑')
})
it('租户切换取消容量读取并关闭编辑器，忽略迟到保存', async () => {
  let resolve!: (value: typeof capacity) => void
  vi.mocked(fileDocumentsApi.saveCapacity).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const { wrapper, tenants } = await setup('capacity', ['file:read', 'file:upload'], true)
  await button(wrapper, '容量管理').trigger('click'); await flushPromises(); await wrapper.get('input[role="spinbutton"]').setValue('2')
  await wrapper.get('form').trigger('submit'); tenants.currentId = 'new'; await flushPromises()
  resolve({ ...capacity, limit_bytes: 999 }); await flushPromises()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false); expect(wrapper.text()).not.toContain('999')
})
it('容量读取失败可刷新恢复，权限撤销取消当前读取', async () => {
  vi.mocked(fileDocumentsApi.capacity).mockRejectedValueOnce(new Error('offline'))
  const { wrapper, auth } = await setup('capacity'); expect(wrapper.text()).toContain('容量读取失败')
  await button(wrapper, '刷新').trigger('click'); await flushPromises(); expect(wrapper.text()).toContain('已使用 12 B')
  const signal = vi.mocked(fileDocumentsApi.capacity).mock.calls.at(-1)![1]!
  auth.user!.permissions = []; await flushPromises(); expect(signal.aborted).toBe(true); expect(wrapper.text()).toBe('')
})
