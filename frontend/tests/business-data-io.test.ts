import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { ElButton } from 'element-plus'
import BusinessDataIO from '../src/components/codegen/BusinessDataIO.vue'
import { businessDataIO as api } from '../src/api/businessDataIO'
import { useAuthStore } from '../src/stores/auth'
import { useModuleStore } from '../src/stores/modules'
import { useTenantStore } from '../src/stores/tenants'

vi.mock('../src/api/businessDataIO', () => ({ businessDataIO: { catalog: vi.fn(), inspect: vi.fn(), preview: vi.fn(), submit: vi.fn(), task: vi.fn(), mappings: vi.fn(), save: vi.fn(), remove: vi.fn(), errors: vi.fn(), previewErrors: vi.fn(), export: vi.fn(), startExport: vi.fn(), exportTask: vi.fn(), exportDownload: vi.fn() } }))
const catalog = { fields: [{ name: 'code', label: '编号', required: true, key: true }, { name: 'name', label: '名称', required: true, key: false }], modes: ['create', 'skip', 'update'], max_rows: 5000, max_bytes: 10485760 }
const preview = { id: 'plan-1', summary: { total: 2, created: 1, updated: 0, skipped: 0, failed: 1 }, errors: [{ row: 3, message: 'row_validation_failed' }], expires_at: '2026-10-18T15:00:00Z' }
function setup() {
  const auth = useAuthStore(), modules = useModuleStore(), tenants = useTenantStore()
  auth.token = 'test-session'; auth.user = { id: 'one', username: 'one', email: '', avatar: '', permissions: ['data_io:import', 'data_io:export', 'cg_suppliers:read', 'cg_suppliers:create', 'cg_suppliers:update'] }
  modules.config = { contract_version: 1, preset: 'standard', modules: ['data_io', 'cg_suppliers'].map(key => ({ key, title: key, enabled: true, paths: [], dependencies: [] })) }
  const wrapper = mount(BusinessDataIO, { props: { resource: 'cg_suppliers', filters: { code: 'A' } }, global: { components: { ElButton }, stubs: { BaseDialog: { props: ['modelValue'], template: '<section v-if="modelValue"><slot/><slot name="footer"/></section>' } } } })
  const button = (name: string) => wrapper.findAll('button').find(item => item.text() === name)!
  const open = async () => { await button('业务导入').trigger('click'); await flushPromises() }
  const select = async (name = 'rows.csv', body = '编号,名称\nA,甲\n') => {
    const input = wrapper.get('input[type=file]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [new File([body], name)] })
    await input.trigger('change'); await flushPromises()
  }
  return { wrapper, auth, modules, tenants, button, open, select }
}
beforeEach(() => {
  localStorage.clear(); setActivePinia(createPinia()); vi.resetAllMocks()
  vi.stubGlobal('URL', class extends URL { static createObjectURL = vi.fn(() => 'blob:business-data'); static revokeObjectURL = vi.fn() })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  vi.mocked(api.catalog).mockResolvedValue(catalog); vi.mocked(api.mappings).mockResolvedValue([])
  vi.mocked(api.inspect).mockResolvedValue({ headers: ['编号', '名称'], rows: 2 }); vi.mocked(api.preview).mockResolvedValue(preview)
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('列映射→预检不提交→确认→刷新结果及错误行下载，预检选项被冻结', async () => {
  vi.mocked(api.submit).mockResolvedValue({ id: 'task-1', status: 'pending', progress: 0, result: {} })
  vi.mocked(api.task).mockResolvedValue({ id: 'task-1', status: 'success', progress: 100, result: preview.summary })
  vi.mocked(api.errors).mockResolvedValue(new Blob(['row,error']))
  const { wrapper, button, open, select } = setup(); await open(); await select()
  expect(button('只校验预览').attributes('disabled')).toBeUndefined()
  await button('只校验预览').trigger('click'); await flushPromises()
  expect(api.preview).toHaveBeenCalledWith('cg_suppliers', expect.any(File), { mapping: { 编号: 'code', 名称: 'name' }, key: 'code', mode: 'create' }, expect.any(AbortSignal))
  expect(api.submit).not.toHaveBeenCalled(); expect(wrapper.text()).toContain('第 3 行')
  expect(wrapper.find('select').exists()).toBe(false)
  await button('确认执行导入').trigger('click'); await flushPromises()
  expect(api.submit).toHaveBeenCalledWith('plan-1', expect.any(AbortSignal))
  await button('刷新导入结果').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('已完成'); expect(wrapper.emitted('completed')).toHaveLength(1)
  await button('下载错误行').trigger('click'); await flushPromises()
  expect(api.errors).toHaveBeenCalledWith('task-1', expect.any(AbortSignal)); expect(URL.revokeObjectURL).toHaveBeenCalledOnce()
})

it('保存并应用个人模板，缺少必填映射或列重复时不能预检', async () => {
  const { wrapper, button, open, select } = setup(); await open(); await select()
  const mappedName = wrapper.get('select[aria-label="映射列 名称"]')
  await mappedName.setValue('code'); expect(button('只校验预览').attributes('disabled')).toBeDefined()
  await mappedName.setValue(''); expect(button('只校验预览').attributes('disabled')).toBeDefined()
  await mappedName.setValue('name')
  await wrapper.get('input[maxlength="80"]').setValue('我的模板')
  vi.mocked(api.save).mockResolvedValue({ id: 'mapping-1', name: '我的模板', options: { mapping: { 编号: 'code', 名称: 'name' }, key: 'code', mode: 'skip' } })
  await button('保存个人模板').trigger('click'); await flushPromises()
  expect(api.save).toHaveBeenCalledOnce()
  await button('删除模板').trigger('click'); await flushPromises(); expect(api.remove).toHaveBeenCalledWith('mapping-1', expect.any(AbortSignal))
})

it('全部行预检失败也可下载完整错误文件，无需写入或提交任务', async () => {
  vi.mocked(api.preview).mockResolvedValue({ ...preview, summary: { total: 105, created: 0, updated: 0, skipped: 0, failed: 105 } })
  vi.mocked(api.previewErrors).mockResolvedValue(new Blob(['failed rows']))
  const { button, open, select } = setup(); await open(); await select()
  await button('只校验预览').trigger('click'); await flushPromises()
  expect(button('确认执行导入').attributes('disabled')).toBeDefined()
  await button('下载错误行').trigger('click'); await flushPromises()
  expect(api.previewErrors).toHaveBeenCalledWith('plan-1', expect.any(AbortSignal))
  expect(api.submit).not.toHaveBeenCalled()
})

it.each(['account', 'permissions', 'tenant', 'module', 'unmount'])('预检等待时%s变化取消并丢弃迟到结果', async kind => {
  let done!: (value: typeof preview) => void
  vi.mocked(api.preview).mockReturnValue(new Promise(resolve => { done = resolve }))
  const { wrapper, button, open, select, auth, tenants, modules } = setup(); await open(); await select()
  await button('只校验预览').trigger('click')
  const signal = vi.mocked(api.preview).mock.calls[0]![3]!
  if (kind === 'account') auth.user!.id = 'two'
  if (kind === 'permissions') auth.user!.permissions = []
  if (kind === 'tenant') tenants.currentId = 'another'
  if (kind === 'module') modules.config!.modules[0]!.enabled = false
  if (kind === 'unmount') wrapper.unmount()
  expect(signal.aborted).toBe(true); done(preview); await flushPromises()
  expect(api.submit).not.toHaveBeenCalled()
  if (kind !== 'unmount') expect(wrapper.text()).not.toContain('第 3 行')
})

it('导出只传当前筛选并释放下载URL；失去权限立即隐藏入口', async () => {
  vi.mocked(api.startExport).mockResolvedValue({ id: 'export-1', status: 'pending', progress: 0, result: { documents: 1 } })
  vi.mocked(api.exportTask).mockResolvedValue({ id: 'export-1', status: 'success', progress: 100, result: { documents: 1, rows: 1, expires_at: '2099-01-01T00:00:00Z' } })
  vi.mocked(api.exportDownload).mockResolvedValue(new Blob(['code\nA']))
  const { wrapper, button, auth } = setup()
  await button('后台导出 CSV').trigger('click'); await flushPromises()
  expect(api.startExport).toHaveBeenCalledWith('cg_suppliers', 'csv', { code: 'A' }, expect.any(AbortSignal))
  expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled()
  await button('刷新导出结果').trigger('click'); await flushPromises()
  await button('下载导出文件').trigger('click'); await flushPromises()
  expect(api.exportDownload).toHaveBeenCalledWith('export-1', expect.any(AbortSignal))
  expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledOnce(); expect(URL.revokeObjectURL).toHaveBeenCalledOnce()
  auth.user!.permissions = []; await flushPromises(); expect(wrapper.find('button').exists()).toBe(false)
})

it('请求失败保留可重试的确认预检，防止重复提交建立新批次', async () => {
  vi.mocked(api.submit).mockRejectedValue(new Error('connection lost'))
  const { wrapper, button, open, select } = setup(); await open(); await select()
  await button('只校验预览').trigger('click'); await flushPromises()
  await button('确认执行导入').trigger('click'); await flushPromises()
  expect(wrapper.get('[role=alert]').text()).toContain('操作失败')
  await button('确认执行导入').trigger('click'); await flushPromises()
  expect(api.preview).toHaveBeenCalledOnce(); expect(api.submit).toHaveBeenCalledTimes(2)
  expect(vi.mocked(api.submit).mock.calls.map(call => call[0])).toEqual(['plan-1', 'plan-1'])
})

it.each([['empty.csv', ''], ['bad.exe', 'data']])('无效文件%s不会上传', async (name, body) => {
  const { wrapper, open, select } = setup(); await open(); await select(name, body)
  expect(api.inspect).not.toHaveBeenCalled(); expect(wrapper.get('[role=alert]').text()).toContain('10 MiB')
})

it('主子表按整单提示、映射命名空间明细并展示单据和源行数，开放后台导出', async () => {
  vi.mocked(api.catalog).mockResolvedValue({ ...catalog, structure: 'master_detail', exportable: true,
    fields: [...catalog.fields, { name: 'lines.product', label: '明细 / 商品', required: true, key: false }] })
  vi.mocked(api.inspect).mockResolvedValue({ headers: ['code', 'name', 'lines.product'], rows: 3 })
  vi.mocked(api.preview).mockResolvedValue({ ...preview, summary: { total: 2, source_rows: 3, created: 1, updated: 0, skipped: 0, failed: 1 }, errors: [{ row: 2, message: 'inconsistent_document_fields' }] })
  const { wrapper, button, open, select } = setup()
  await wrapper.setProps({ structure: 'master_detail' }); await open()
  expect(wrapper.text()).toContain('更新会替换所有明细组')
  expect(wrapper.findAll('button').some(item => item.text() === '后台导出 CSV')).toBe(true)
  await select()
  expect((wrapper.get('select[aria-label="映射列 lines.product"]').element as HTMLSelectElement).value).toBe('lines.product')
  await button('只校验预览').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('总单据数')
  expect(wrapper.text()).toContain('源文件行数：3')
  expect(wrapper.text()).toContain('同一单据的主字段不一致')
  expect(api.export).not.toHaveBeenCalled()
})

it.each(['tenant', 'permissions', 'unmount'])('导出等待时 %s 变化阻止旧产物和迟到状态进入新上下文', async kind => {
  let done!: (value: { id: string; status: string; progress: number; result: object }) => void
  vi.mocked(api.startExport).mockReturnValue(new Promise(resolve => { done = resolve }))
  const { wrapper, button, tenants, auth } = setup()
  await button('后台导出 XLSX').trigger('click')
  const signal = vi.mocked(api.startExport).mock.calls[0]![3]!
  if (kind === 'tenant') tenants.currentId = 'changed'
  if (kind === 'permissions') auth.user!.permissions = []
  if (kind === 'unmount') wrapper.unmount()
  expect(signal.aborted).toBe(true)
  done({ id: 'old-export', status: 'success', progress: 100, result: {} }); await flushPromises()
  expect(api.exportDownload).not.toHaveBeenCalled()
  if (kind !== 'unmount') expect(wrapper.text()).not.toContain('下载导出文件')
})

it('过期成功导出禁用下载，失败导出显示重试提示', async () => {
  vi.mocked(api.startExport).mockResolvedValue({ id: 'expired', status: 'success', progress: 100, result: { expires_at: '2000-01-01T00:00:00Z' } })
  vi.mocked(api.exportTask).mockResolvedValue({ id: 'expired', status: 'failed', progress: 0, result: {} })
  const { wrapper, button } = setup()
  await button('后台导出 CSV').trigger('click'); await flushPromises()
  expect(button('下载导出文件').attributes('disabled')).toBeDefined()
  await button('刷新导出结果').trigger('click'); await flushPromises()
  expect(wrapper.text()).toContain('导出已停止')
})
