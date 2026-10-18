import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import ElementPlus, { ElMessageBox } from 'element-plus'
import FileLibraryToolbar from '../src/components/files/FileLibraryToolbar.vue'
import { fileLibraryApi, type FileLibrary } from '../src/api/fileLibrary'
import type { FileRow } from '../src/api'
import { useAuthStore } from '../src/stores/auth'
import { useModuleStore } from '../src/stores/modules'
import { useTenantStore } from '../src/stores/tenants'

vi.mock('../src/api/fileLibrary', () => ({ fileLibraryApi: { load: vi.fn(), createFolder: vi.fn(), saveFolder: vi.fn(), deleteFolder: vi.fn(), organize: vi.fn() } }))
const Dialog = defineComponent({ props: ['modelValue'], template: '<section v-if="modelValue" role="dialog"><slot /></section>' })
const folder = { id: 'root', name: '合同', parent: null, version: 3 }
const library: FileLibrary = { folders: [folder, { id: 'child', name: '2026', parent: 'root', version: 1 }], tags: ['采购'], tags_truncated: false }
const file = { id: 'file', original_name: '合同.txt', organization: { version: 7, folder: 'child', tags: ['采购'] } } as FileRow
const wrappers: ReturnType<typeof mount>[] = []
beforeEach(() => { vi.resetAllMocks(); localStorage.clear(); setActivePinia(createPinia()); vi.mocked(fileLibraryApi.load).mockResolvedValue(structuredClone(library)) })
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()); vi.restoreAllMocks() })
function token(sid = 'session', session_version = 1, jti = 'initial') { return `header.${btoa(JSON.stringify({ sid, user_id: 'owner', session_version, jti }))}.signature` }
async function setup(access = 'session') {
  const auth = useAuthStore(), tenants = useTenantStore(), modules = useModuleStore()
  auth.token = access; auth.user = { id: 'owner', username: 'owner', email: '', avatar: '', is_staff: false, permissions: [] }
  modules.config = { contract_version: 1, preset: 'standard', modules: [{ key: 'files', title: '文件', enabled: true, dependencies: [], paths: ['/files'] }] }
  const wrapper = mount(FileLibraryToolbar, { props: { file: null }, global: { plugins: [ElementPlus], stubs: { ElDialog: Dialog } } })
  wrappers.push(wrapper); await flushPromises()
  return { wrapper, auth, tenants, modules }
}
function button(wrapper: ReturnType<typeof mount>, label: string) { return wrapper.findAll('button').find(item => item.text() === label)! }
async function newFolder(wrapper: ReturnType<typeof mount>) {
  await button(wrapper, '新建目录').trigger('click'); await wrapper.get('input[aria-label="目录名称"]').setValue('新合同')
}

it('展示个人整理边界和树路径，筛选含关键词且读取可取消', async () => {
  const { wrapper } = await setup()
  expect(wrapper.text()).toContain('目录和标签仅自己可见')
  expect(fileLibraryApi.load).toHaveBeenCalledWith(expect.any(AbortSignal))
  const select = wrapper.findAllComponents({ name: 'ElSelect' })[0]!
  select.vm.$emit('update:modelValue', 'child'); select.vm.$emit('change', 'child')
  await wrapper.get('input[aria-label="文件关键词"]').setValue('采购单'); await wrapper.get('form').trigger('submit')
  expect(wrapper.emitted('filter')!.at(-1)).toEqual([{ folder: 'child', tag: '', search: '采购单' }])
  await button(wrapper, '管理目录').trigger('click'); expect(wrapper.text()).toContain('合同 / 2026')
})

it('新建、版本化编辑且排除自身及后代作为父目录', async () => {
  const { wrapper } = await setup(); await newFolder(wrapper)
  await wrapper.get('[role="dialog"] form').trigger('submit'); await flushPromises()
  expect(fileLibraryApi.createFolder).toHaveBeenCalledWith('新合同', null)
  await button(wrapper, '管理目录').trigger('click')
  await wrapper.findAll('.folder-row')[0]!.findAll('button')[0]!.trigger('click')
  const editor = wrapper.findAll('[role="dialog"]').at(-1)!
  await editor.get('[role="combobox"]').trigger('click'); await flushPromises()
  expect(editor.get('[role="combobox"]').attributes('aria-expanded')).toBe('true')
  const options = document.getElementById(editor.get('[role="combobox"]').attributes('aria-controls')!)!
  expect(options.textContent).toContain('根目录'); expect(options.textContent).not.toContain('合同')
  await editor.get('input').setValue('归档'); await editor.get('form').trigger('submit'); await flushPromises()
  expect(fileLibraryApi.saveFolder).toHaveBeenCalledWith(expect.objectContaining({ ...folder, name: '归档' }), '归档', null)
})
it('正常令牌轮换保留目录草稿和筛选，进行中的保存继续成功', async () => {
  let resolve!: (value: typeof folder) => void
  vi.mocked(fileLibraryApi.createFolder).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const { wrapper, auth } = await setup(token()); await newFolder(wrapper)
  await wrapper.get('input[aria-label="文件关键词"]').setValue('待办合同')
  await wrapper.get('[role="dialog"] form').trigger('submit')
  const closeCount = wrapper.emitted('close')?.length ?? 0
  auth.token = token('session', 1, 'rotated'); await flushPromises()
  expect(wrapper.get('input[aria-label="目录名称"]').element).toHaveProperty('value', '新合同')
  expect(wrapper.get('input[aria-label="文件关键词"]').element).toHaveProperty('value', '待办合同')
  expect(wrapper.emitted('close')?.length ?? 0).toBe(closeCount)
  expect(fileLibraryApi.load).toHaveBeenCalledTimes(1)
  resolve(folder); await flushPromises()
  expect(wrapper.emitted('updated')).toHaveLength(1)
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
})

it('整理提交带独立版本和标签；失败保留输入并可重试', async () => {
  const { wrapper } = await setup(); await wrapper.setProps({ file })
  vi.mocked(fileLibraryApi.organize).mockRejectedValueOnce(new Error('标签格式无效'))
  await wrapper.get('[role="dialog"] form').trigger('submit'); await flushPromises()
  expect(fileLibraryApi.organize).toHaveBeenCalledWith('file', { version: 7, folder: 'child', tags: ['采购'] })
  expect(wrapper.get('[role="alert"]').text()).toContain('标签格式无效')
  expect(wrapper.find('[role="dialog"] form').exists()).toBe(true)
  await wrapper.get('[role="dialog"] form').trigger('submit'); await flushPromises()
  expect(wrapper.emitted('updated')).toHaveLength(1)
})

it('读取失败禁用写入并提供重试，恢复后可新建', async () => {
  vi.mocked(fileLibraryApi.load).mockRejectedValueOnce(new Error('offline'))
  const { wrapper } = await setup()
  expect(button(wrapper, '新建目录').attributes('disabled')).toBeDefined()
  await button(wrapper, '重试').trigger('click'); await flushPromises()
  expect(button(wrapper, '新建目录').attributes('disabled')).toBeUndefined()
})

it('提交中阻止重复写入和关闭；409关闭旧草稿并刷新版本', async () => {
  let reject!: (value: unknown) => void
  vi.mocked(fileLibraryApi.createFolder).mockImplementationOnce(() => new Promise((_, done) => { reject = done }))
  const { wrapper } = await setup(); await newFolder(wrapper)
  await wrapper.get('[role="dialog"] form').trigger('submit'); await wrapper.get('[role="dialog"] form').trigger('submit')
  expect(fileLibraryApi.createFolder).toHaveBeenCalledTimes(1)
  expect(button(wrapper, '取消').attributes('disabled')).toBeDefined()
  reject({ response: { status: 409 } }); await flushPromises()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  expect(fileLibraryApi.load).toHaveBeenCalledTimes(2)
})

it.each(['tenant', 'session', 'permission', 'module', 'password'] as const)('%s变化清空目录与筛选，丢弃迟到读取', async change => {
  let resolve!: (value: FileLibrary) => void
  vi.mocked(fileLibraryApi.load).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const { wrapper, auth, tenants, modules } = await setup()
  const signal = vi.mocked(fileLibraryApi.load).mock.calls[0]![0]!
  vi.mocked(fileLibraryApi.load).mockResolvedValue({ folders: [], tags: [], tags_truncated: false })
  if (change === 'tenant') tenants.currentId = 'new-tenant'
  if (change === 'session') auth.token = 'new-session'
  if (change === 'permission') auth.user!.permissions = ['file:download']
  if (change === 'module') modules.config!.modules[0]!.enabled = false
  if (change === 'password') auth.user!.must_change_password = true
  await flushPromises(); expect(signal.aborted).toBe(true)
  resolve(library); await flushPromises()
  await button(wrapper, '管理目录').trigger('click'); expect(wrapper.text()).not.toContain('合同 / 2026')
  expect(wrapper.emitted('filter')!.at(-1)).toEqual([{ folder: '', tag: '', search: '' }])
})

it('身份变更或卸载后，迟到写入不通知、不刷新其他身份', async () => {
  let resolve!: (value: typeof folder) => void
  vi.mocked(fileLibraryApi.createFolder).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const { wrapper, tenants } = await setup(); await newFolder(wrapper)
  await wrapper.get('[role="dialog"] form').trigger('submit'); tenants.currentId = 'new'
  await flushPromises(); const reads = vi.mocked(fileLibraryApi.load).mock.calls.length
  resolve(folder); await flushPromises()
  expect(fileLibraryApi.load).toHaveBeenCalledTimes(reads); expect(wrapper.emitted('updated')).toBeUndefined()
  await newFolder(wrapper); await wrapper.get('[role="dialog"] form').trigger('submit'); wrapper.unmount(); await flushPromises()
  expect(wrapper.emitted('updated')).toBeUndefined()
})

it('删除目录需确认且携带版本，成功后刷新而不调用文件删除', async () => {
  // Element Plus 的重载返回类型交叉；确认框实际 resolve 的值为 confirm。
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as Awaited<ReturnType<typeof ElMessageBox.confirm>>)
  const { wrapper } = await setup(); await button(wrapper, '管理目录').trigger('click')
  await wrapper.findAll('.folder-row')[0]!.findAll('button')[1]!.trigger('click'); await flushPromises()
  expect(ElMessageBox.confirm).toHaveBeenCalledWith(expect.stringContaining('不删除文件'), expect.any(String), expect.any(Object))
  expect(fileLibraryApi.deleteFolder).toHaveBeenCalledWith(expect.objectContaining(folder)); expect(wrapper.emitted('updated')).toHaveLength(1)
})
