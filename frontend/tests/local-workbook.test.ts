import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { ElButton } from 'element-plus'
import { read, utils } from 'xlsx'
import LocalExportButton from '../src/components/common/LocalExportButton.vue'
import { snapshotWorkbook, LocalWorkbookError, validateWorkbookSnapshot } from '../src/utils/localWorkbook'
import { writeLocalWorkbook } from '../src/utils/writeLocalWorkbook'
import { useAuthStore } from '../src/stores/auth'
import { useModuleStore } from '../src/stores/modules'
import { i18n } from '../src/i18n'
import type { PrintCell } from '../src/utils/printDocument'

const options = { title: '用户列表', rows: [{ name: '=HYPERLINK("https://evil.test","中文")', secret: 'never-export-private-field' }], columns: [{ label: '名字', value: (row: { name: string }) => row.name }], currentPage: 3, locale: 'zh-CN' }

describe('真实 XLSX 写出与白名单边界', () => {
  it('原样保存公式样式文本、中文换行和数字，不产生公式或链接，排除未登记字段', () => {
    const values = ['=HYPERLINK("https://evil.test","go")', '+SUM(1,2)', '-1+2', '@SUM(1,2)', '\t=1+1', '<script>alert(1)</script>', 'https://evil.test', '中文😀\n第二行', '0000123', '9007199254740993']
    const snapshot = snapshotWorkbook({ ...options, rows: values.map(name => ({ name, secret: 'not-allowed' })) })
    const workbook = read(writeLocalWorkbook(snapshot), { type: 'array', cellNF: true })
    expect(workbook.SheetNames).toEqual(['Data', 'Export info'])
    expect(utils.sheet_to_json(workbook.Sheets.Data!, { header: 1 })).toEqual([['名字'], ...values.map(value => [value])])
    for (let i = 2; i <= values.length + 1; i++) {
      const cell = workbook.Sheets.Data![`A${i}`]!
      expect(cell.t).toBe('s'); expect(cell.f).toBeUndefined(); expect(cell.l).toBeUndefined()
    }
    const metadata = utils.sheet_to_json(workbook.Sheets['Export info']!, { header: 1 })
    expect(metadata).toContainEqual(['当前页', '3'])
    expect(metadata).toContainEqual(['记录数', String(values.length)])
    expect(JSON.stringify(workbook)).not.toContain('not-allowed')
    expect(JSON.stringify(workbook)).not.toContain('never-export-private-field')
  })

  it('英文元信息、有限数值/布尔/日期/空值转换；快照与原行互不关联', () => {
    const row = { name: 'initial' }
    const snapshot = snapshotWorkbook({ ...options, rows: [row], locale: 'en-US' })
    row.name = 'changed'
    expect(snapshot.rows).toEqual([['initial']])
    const workbook = read(writeLocalWorkbook(snapshot), { type: 'array' })
    expect(utils.sheet_to_json(workbook.Sheets['Export info']!, { header: 1 })).toContainEqual(['Current page', '3'])
    const values = [null, undefined, false, 0, new Date('2026-10-15T01:00:00Z')]
    expect(snapshotWorkbook({ ...options, columns: values.map(value => ({ label: '值', value: () => value })) }).rows).toEqual([['', '', 'false', '0', '2026-10-15T01:00:00.000Z']])
  })

  it.each([
    ['object', { secret: 'hidden' }], ['array', ['hidden']], ['function', () => 'hidden'], ['infinity', Infinity], ['nan', NaN],
    ['invalid-date', new Date('invalid')], ['long', 'x'.repeat(10001)], ['control', 'unsafe\u0000'], ['surrogate', '\ud800'],
  ])('拒绝不支持的单元格 %s，不静默序列化或截断', (_name, value) => {
    expect(() => snapshotWorkbook({ ...options, columns: [{ label: '值', value: () => value as PrintCell }] })).toThrow(LocalWorkbookError)
  })

  it('行/列/总文字上限、空数据、无效页号与Worker直接输入校验', () => {
    expect(() => snapshotWorkbook({ ...options, rows: Array.from({ length: 101 }, () => options.rows[0]!) })).toThrow(LocalWorkbookError)
    expect(() => snapshotWorkbook({ ...options, columns: Array.from({ length: 21 }, () => options.columns[0]!) })).toThrow(LocalWorkbookError)
    expect(() => snapshotWorkbook({ ...options, rows: [] })).toThrow(LocalWorkbookError)
    expect(() => snapshotWorkbook({ ...options, currentPage: 0 })).toThrow(LocalWorkbookError)
    expect(() => snapshotWorkbook({ ...options, rows: Array.from({ length: 100 }, () => ({ name: 'x'.repeat(10000) })) })).toThrow(LocalWorkbookError)
    for (const value of [null, [], {}, { ...snapshotWorkbook(options), rows: [[{ formula: '=1+1' }]] }, { ...snapshotWorkbook(options), rows: [['valid', 'unexpected']] }]) {
      expect(() => writeLocalWorkbook(value)).toThrow(LocalWorkbookError)
    }
    expect(() => validateWorkbookSnapshot(snapshotWorkbook(options))).not.toThrow()
  })
})

class FakeWorker {
  static instances: FakeWorker[] = []
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: ErrorEvent) => void) | null = null
  onmessageerror: (() => void) | null = null
  terminate = vi.fn()
  postMessage = vi.fn()
  constructor() { FakeWorker.instances.push(this) }
}
function setup() {
  const auth = useAuthStore(), modules = useModuleStore()
  auth.token = 'local-export-fixture'
  auth.user = { id: 'member', username: 'member', email: '', avatar: '', permissions: ['user:read', 'data_io:export'] }
  modules.config = { contract_version: 1, preset: 'standard', modules: [{ key: 'data_io', title: '', enabled: true, paths: [], dependencies: [] }] }
  const wrapper = mount(LocalExportButton<{ name: string }>, { props: { ...options, resource: 'users' }, global: { plugins: [i18n], components: { ElButton } } })
  return { auth, modules, wrapper }
}

describe('本地导出 Worker 与认证生命周期', () => {
  beforeEach(() => {
    localStorage.clear(); setActivePinia(createPinia()); i18n.global.locale.value = 'zh-CN'; vi.useFakeTimers()
    FakeWorker.instances = []; vi.stubGlobal('Worker', FakeWorker)
    vi.stubGlobal('URL', class extends URL { static createObjectURL = vi.fn(() => 'blob:local-export'); static revokeObjectURL = vi.fn() })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  })
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

  it('点击才创建Worker、只发送字段快照，重复点击不重复创建；下载并终止释放', async () => {
    const { wrapper } = setup()
    expect(FakeWorker.instances).toHaveLength(0)
    await wrapper.get('button').trigger('click'); await wrapper.get('button').trigger('click')
    expect(FakeWorker.instances).toHaveLength(1)
    const worker = FakeWorker.instances[0]!
    expect(JSON.stringify(worker.postMessage.mock.calls)).not.toContain('never-export-private-field')
    worker.onmessage!(new MessageEvent('message', { data: { ok: true, bytes: new ArrayBuffer(32) } }))
    await flushPromises()
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledOnce()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:local-export')
    expect(worker.terminate).toHaveBeenCalledOnce()
    expect(worker.onmessage).toBeNull()
    expect(vi.getTimerCount()).toBe(0)
    expect(wrapper.get('button').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it.each(['identity', 'token', 'permissions', 'module', 'owner', 'page', 'rows', 'loading', 'locale', 'unmount'] as const)('%s 变化时终止并拒绝晚到结果', async kind => {
    const { wrapper, auth, modules } = setup()
    await wrapper.get('button').trigger('click')
    const worker = FakeWorker.instances[0]!, late = worker.onmessage!
    if (kind === 'identity') auth.user!.id = 'other'
    if (kind === 'token') auth.token = 'other-token'
    if (kind === 'permissions') auth.user!.permissions = ['user:read']
    if (kind === 'module') modules.config!.modules[0]!.enabled = false
    if (kind === 'owner') await wrapper.setProps({ ownerKey: 'other' })
    if (kind === 'page') await wrapper.setProps({ currentPage: 2 })
    if (kind === 'rows') await wrapper.setProps({ rows: [{ name: 'other' }] })
    if (kind === 'loading') await wrapper.setProps({ loading: true })
    if (kind === 'locale') i18n.global.locale.value = 'en-US'
    if (kind === 'unmount') wrapper.unmount()
    expect(worker.terminate).toHaveBeenCalledOnce()
    late(new MessageEvent('message', { data: { ok: true, bytes: new ArrayBuffer(32) } }))
    await flushPromises()
    expect(URL.createObjectURL).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
    if (kind !== 'unmount') wrapper.unmount()
  })

  it.each(['failure', 'invalid', 'timeout', 'cancel', 'bad-output'] as const)('%s 后解除锁并可重试，不下载部分数据', async kind => {
    const { wrapper } = setup()
    await wrapper.get('button').trigger('click')
    const worker = FakeWorker.instances[0]!
    if (kind === 'failure') worker.onerror!(new ErrorEvent('error'))
    if (kind === 'invalid') worker.onmessage!(new MessageEvent('message', { data: { ok: false, reason: 'invalid' } }))
    if (kind === 'timeout') vi.advanceTimersByTime(15000)
    if (kind === 'cancel') await wrapper.findAll('button')[1]!.trigger('click')
    if (kind === 'bad-output') worker.onmessage!(new MessageEvent('message', { data: { ok: true, bytes: new ArrayBuffer(10 * 1024 * 1024 + 1) } }))
    await flushPromises()
    expect(worker.terminate).toHaveBeenCalledOnce(); expect(URL.createObjectURL).not.toHaveBeenCalled()
    expect(wrapper.find('[role="alert"]').exists()).toBe(kind !== 'cancel')
    expect(wrapper.get('button').attributes('disabled')).toBeUndefined()
    await wrapper.get('button').trigger('click')
    expect(FakeWorker.instances).toHaveLength(2)
    wrapper.unmount(); expect(vi.getTimerCount()).toBe(0)
  })

  it('无导出权限或模块关闭无入口，空页和加载中禁用，超限整体拒绝', async () => {
    const { wrapper, auth, modules } = setup()
    auth.user!.permissions = ['user:read']; await flushPromises(); expect(wrapper.find('button').exists()).toBe(false)
    auth.user!.permissions = ['user:read', 'data_io:export']; modules.config!.modules[0]!.enabled = false
    await flushPromises(); expect(wrapper.find('button').exists()).toBe(false)
    modules.config!.modules[0]!.enabled = true
    await wrapper.setProps({ rows: [] }); expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    await wrapper.setProps({ rows: options.rows, loading: true }); expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    await wrapper.setProps({ loading: false, rows: Array.from({ length: 101 }, () => options.rows[0]!) })
    await wrapper.get('button').trigger('click')
    expect(wrapper.get('[role="alert"]').text()).toContain('超出')
    expect(FakeWorker.instances).toHaveLength(0)
    wrapper.unmount()
  })
})
