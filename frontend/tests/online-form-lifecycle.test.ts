import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { useAuthStore } from '../src/stores/auth'
import { useTenantStore } from '../src/stores/tenants'
import { onlineFormLifecycleApi } from '../src/api/onlineFormLifecycle'
import { onlineFormsApi } from '../src/api'
import { onlineFormAttachmentsApi } from '../src/api/onlineFormAttachments'
import Records from '../src/components/onlineForms/OnlineFormRecords.vue'
import Runtime from '../src/views/onlineForms/OnlineFormRuntimeView.vue'
import Designer from '../src/views/onlineForms/OnlineFormDesignerView.vue'
vi.mock('../src/components/layout/AppLayout.vue', () => ({ default: defineComponent({ template: '<main><slot /></main>' }) }))
vi.mock('../src/api/onlineFormLifecycle', () => ({ onlineFormLifecycleApi: { records: vi.fn(), detail: vi.fn(), update: vi.fn(), newVersion: vi.fn(), approvalFlows: vi.fn(), submitApproval: vi.fn(), withdrawApproval: vi.fn() } }))
vi.mock('../src/api/onlineFormAttachments', () => ({ onlineFormAttachmentsApi: { choices: vi.fn(), validatePreview: vi.fn() } }))
vi.mock('../src/api', () => ({ onlineFormsApi: { list: vi.fn(), published: vi.fn(), createRecord: vi.fn(), create: vi.fn(), update: vi.fn(), publish: vi.fn(), validate: vi.fn() } }))
const oldDefinition = { schema_version: 2, fields: [{ key: 'old_title', label: '旧版标题', type: 'text', required: true }] }
const row = { id: 'record-1', form: 'release-1', form_name: '费用申请', release_number: 1, form_status: 'archived', form_version: 7, version: 2, data: { old_title: '历史内容' }, definition_snapshot: oldDefinition, created_at: '2026-10-18T00:00:00Z' }
const page = (items: unknown[] = [row]) => ({ items, pagination: { total: items.length, page: 1, page_size: 20 } })
const wrappers: VueWrapper[] = []
beforeEach(() => {
  vi.resetAllMocks(); localStorage.clear()
  vi.mocked(onlineFormLifecycleApi.records).mockResolvedValue(page() as never)
  vi.mocked(onlineFormLifecycleApi.detail).mockResolvedValue(row as never)
})
afterEach(() => { for (const wrapper of wrappers.splice(0)) wrapper.unmount(); vi.restoreAllMocks(); document.body.innerHTML = ''; localStorage.clear() })
async function harness(component: typeof Records | typeof Runtime | typeof Designer = Records) {
  const pinia = createPinia(), auth = useAuthStore(pinia), tenants = useTenantStore(pinia)
  auth.token = 'isolated'; auth.user = { id: 'owner', username: 'owner', email: '', avatar: '', is_staff: true, permissions: ['*'] }
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/online-forms/:code?', component: { template: '<div />' } }, { path: '/other', component: { template: '<div />' } }] })
  await router.push('/online-forms/expense')
  const wrapper = mount(component, { props: component === Records ? { code: 'expense' } : undefined, attachTo: document.body, global: { plugins: [pinia, router, ElementPlus] } })
  wrappers.push(wrapper); await flushPromises(); return { wrapper, auth, tenants, router }
}
const button = (wrapper: VueWrapper, text: string) => wrapper.findAll('button').find(item => item.text() === text)!
async function open(wrapper: VueWrapper) { await button(wrapper, '查看记录').trigger('click'); await flushPromises() }
const dialog = () => document.body.querySelector('.el-dialog')!
const clickDialog = async (text: string) => { (Array.from(dialog().querySelectorAll('button')).find(item => item.textContent?.trim() === text) as HTMLButtonElement).click(); await flushPromises() }
it('历史详情使用冻结字段，保存携带记录版本，冲突不丢输入，成功不关闭详情', async () => {
  vi.mocked(onlineFormLifecycleApi.update).mockRejectedValueOnce({ isAxiosError: true, response: { data: { message: '记录已变化，请刷新后重试' } } }).mockResolvedValueOnce({ ...row, version: 3, data: { old_title: '保留修改' } } as never)
  const { wrapper } = await harness(); await open(wrapper)
  expect(dialog().textContent).toContain('旧版标题'); expect(dialog().querySelector('input')!.disabled).toBe(true)
  await clickDialog('修改记录')
  const input = dialog().querySelector('input')!; input.value = '保留修改'; input.dispatchEvent(new Event('input', { bubbles: true })); await nextTick()
  await clickDialog('保存记录')
  expect(onlineFormLifecycleApi.update).toHaveBeenLastCalledWith('expense', 'record-1', { old_title: '保留修改' }, 2)
  expect(dialog().querySelector('input')!.value).toBe('保留修改'); expect(dialog().textContent).toContain('记录已变化')
  expect(document.activeElement?.getAttribute('role')).toBe('alert')
  await clickDialog('保存记录'); expect(dialog().textContent).toContain('记录已保存'); expect(dialog().querySelector('input')!.disabled).toBe(true)
})
it('放弃修改选择取消后详情与输入保留，权限变化清空详情，重新打开后只读', async () => {
  vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue('cancel')
  const { wrapper, auth } = await harness(); await open(wrapper); await clickDialog('修改记录')
  const input = dialog().querySelector('input')!; input.value = '尚未保存'; input.dispatchEvent(new Event('input', { bubbles: true })); await nextTick()
  await clickDialog('关闭'); expect(dialog().querySelector('input')!.value).toBe('尚未保存')
  auth.user = { ...auth.user!, permissions: ['online_form:record_read'] }; await flushPromises()
  expect(document.body.textContent).not.toContain('尚未保存'); await button(wrapper, '刷新记录').trigger('click'); await flushPromises(); await open(wrapper)
  expect(dialog().querySelector('input')!.value).toBe('历史内容'); expect(dialog().querySelector('input')!.disabled).toBe(true); expect(dialog().textContent).not.toContain('保存记录')
})
it('撤销读取权限清除历史记录，迟到详情不得恢复', async () => {
  let resolve!: (value: never) => void
  vi.mocked(onlineFormLifecycleApi.detail).mockReturnValue(new Promise(r => { resolve = r }))
  const { wrapper, auth } = await harness(); await open(wrapper)
  auth.user = { ...auth.user!, permissions: [] }; await flushPromises(); resolve(row as never); await flushPromises()
  expect(wrapper.text()).not.toContain('费用申请'); expect(document.body.textContent).not.toContain('历史内容')
})
it('租户切换同步清空旧记录与详情，旧请求迟到不覆盖新租户', async () => {
  let resolveList!: (value: never) => void, resolveDetail!: (value: never) => void
  const { wrapper, tenants } = await harness()
  vi.mocked(onlineFormLifecycleApi.detail).mockReturnValueOnce(new Promise(r => { resolveDetail = r }))
  await open(wrapper)
  vi.mocked(onlineFormLifecycleApi.records).mockReturnValueOnce(new Promise(r => { resolveList = r })).mockResolvedValueOnce(page([]) as never)
  await button(wrapper, '刷新记录').trigger('click'); tenants.currentId = 'tenant-b'; await flushPromises()
  resolveList(page() as never); resolveDetail(row as never); await flushPromises()
  expect(wrapper.text()).not.toContain('费用申请'); expect(document.body.textContent).not.toContain('历史内容')
})
it('归档后没有当前表单仍能查看历史记录，实际提交明确携带表单版本 ID', async () => {
  vi.mocked(onlineFormsApi.published).mockRejectedValueOnce(new Error('没有当前表单'))
  const { wrapper } = await harness(Runtime); expect(wrapper.text()).toContain('我的表单记录'); await open(wrapper); expect(dialog().textContent).toContain('旧版标题')
  wrapper.unmount(); wrappers.splice(wrappers.indexOf(wrapper), 1)
  vi.mocked(onlineFormsApi.published).mockResolvedValueOnce({ data: { data: { id: 'release-2', name: '新版', code: 'expense', status: 'published', version: 1, definition: oldDefinition } } } as never)
  vi.mocked(onlineFormsApi.createRecord).mockResolvedValueOnce({} as never)
  const second = await harness(Runtime); await second.wrapper.get('input').setValue('新版提交'); await button(second.wrapper, '提交').trigger('click'); await flushPromises()
  expect(onlineFormsApi.createRecord).toHaveBeenCalledWith('expense', { old_title: '新版提交' }, expect.any(String), 'release-2')
})
it('同编码下一版以已发布版本为源，创建后进入新版草稿并锁定编码', async () => {
  const source = { id: 'release-1', name: '表单', code: 'expense', status: 'published', version: 7, release_number: 1, definition: oldDefinition }
  const draft = { ...source, id: 'release-2', status: 'draft', version: 1, release_number: 2 }
  vi.mocked(onlineFormsApi.list).mockResolvedValue({ items: [source], pagination: { total: 1 } } as never)
  vi.mocked(onlineFormLifecycleApi.newVersion).mockResolvedValue(draft as never)
  const { wrapper } = await harness(Designer); await wrapper.get('tbody tr').trigger('click'); await flushPromises()
  await button(wrapper, '创建下一版').trigger('click'); await flushPromises()
  expect(onlineFormLifecycleApi.newVersion).toHaveBeenCalledWith('release-1', 7)
  expect(wrapper.findAll('input').some(item => item.element.value === 'expense' && item.attributes('disabled') !== undefined)).toBe(true)
  expect(button(wrapper, '发布').exists()).toBe(true)
})

it('切换租户后迟到的新版本响应不能恢复设计器的旧租户编辑区', async () => {
  const source = { id: 'release-1', name: '旧租户表单', code: 'expense', status: 'published', version: 7, definition: oldDefinition }
  vi.mocked(onlineFormsApi.list).mockResolvedValueOnce({ items: [source], pagination: { total: 1 } } as never).mockResolvedValue({ items: [], pagination: { total: 0 } } as never)
  let resolve!: (value: never) => void
  vi.mocked(onlineFormLifecycleApi.newVersion).mockReturnValue(new Promise(r => { resolve = r }))
  const { wrapper, tenants } = await harness(Designer); await wrapper.get('tbody tr').trigger('click'); await flushPromises()
  await button(wrapper, '创建下一版').trigger('click'); tenants.currentId = 'tenant-b'; await flushPromises()
  resolve({ ...source, id: 'release-2', status: 'draft' } as never); await flushPromises()
  expect(wrapper.text()).not.toContain('旧租户表单'); expect(wrapper.findAll('input')).toHaveLength(0)
})
it('切换租户后迟到的提交结果不能清空新表单或显示旧提交成功', async () => {
  const form = { id: 'release-1', name: '旧租户', code: 'expense', status: 'published', version: 1, definition: oldDefinition }
  vi.mocked(onlineFormsApi.published).mockResolvedValueOnce({ data: { data: form } } as never).mockResolvedValueOnce({ data: { data: { ...form, id: 'release-b', name: '新租户' } } } as never)
  let resolve!: (value: never) => void
  vi.mocked(onlineFormsApi.createRecord).mockReturnValue(new Promise(r => { resolve = r }))
  const { wrapper, tenants } = await harness(Runtime); await wrapper.get('input').setValue('旧提交'); await button(wrapper, '提交').trigger('click')
  tenants.currentId = 'tenant-b'; await flushPromises(); resolve({} as never); await flushPromises()
  expect(wrapper.text()).toContain('新租户'); expect(wrapper.text()).not.toContain('提交成功')
  expect(wrapper.get('input').element.value).toBe('')
})

it('设计器附件试填携带实际表单 ID，无附件定义保持原校验调用', async () => {
  const attachmentDefinition = { schema_version: 2, fields: [{ key: 'proof', label: '申请附件', type: 'file' }] }
  const form = { id: 'release-files', name: '附件表单', code: 'expense', status: 'draft', version: 1, definition: attachmentDefinition }
  vi.mocked(onlineFormsApi.list).mockResolvedValueOnce({ items: [form], pagination: { total: 1 } } as never)
  const first = await harness(Designer)
  await first.wrapper.get('tbody tr').trigger('click'); await flushPromises()
  await button(first.wrapper, '试填校验').trigger('click'); await flushPromises()
  expect(onlineFormAttachmentsApi.validatePreview).toHaveBeenCalledWith('release-files', expect.objectContaining(attachmentDefinition), {})
  expect(onlineFormsApi.validate).not.toHaveBeenCalled()
  first.wrapper.unmount(); wrappers.splice(wrappers.indexOf(first.wrapper), 1)

  vi.mocked(onlineFormsApi.list).mockResolvedValueOnce({ items: [{ ...form, definition: oldDefinition }], pagination: { total: 1 } } as never)
  const second = await harness(Designer)
  await second.wrapper.get('tbody tr').trigger('click'); await flushPromises()
  await button(second.wrapper, '试填校验').trigger('click'); await flushPromises()
  expect(onlineFormsApi.validate).toHaveBeenCalledWith(expect.objectContaining(oldDefinition), {})
  expect(onlineFormAttachmentsApi.validatePreview).toHaveBeenCalledTimes(1)
})

it('提交与撤回审批携带严格记录版本，审批中锁定输入，撤回后恢复编辑', async () => {
  const draft = { ...row, approval_enabled: true, approval_status: 'draft' }
  const pending = { ...draft, version: 3, approval_status: 'pending', approval_request: 'request-1' }
  vi.mocked(onlineFormLifecycleApi.detail).mockResolvedValue(draft as never)
  vi.mocked(onlineFormLifecycleApi.submitApproval).mockResolvedValue(pending as never)
  vi.mocked(onlineFormLifecycleApi.withdrawApproval).mockResolvedValue({ ...pending, version: 4, approval_status: 'cancelled' } as never)
  const { wrapper } = await harness(); await open(wrapper); await clickDialog('提交审批')
  expect(onlineFormLifecycleApi.submitApproval).toHaveBeenCalledWith('expense', 'record-1', 2)
  expect(dialog().textContent).toContain('审批已提交'); expect(dialog().textContent).not.toContain('修改记录')
  expect(dialog().querySelector('input')!.disabled).toBe(true)
  await clickDialog('撤回审批')
  expect(onlineFormLifecycleApi.withdrawApproval).toHaveBeenCalledWith('expense', 'record-1', 3)
  expect(dialog().textContent).toContain('审批已撤回'); expect(dialog().textContent).toContain('修改记录')
})

it('通过记录不可修改，无提交权限时不显示动作；撤权后迟到审批结果不能恢复详情', async () => {
  vi.mocked(onlineFormLifecycleApi.detail).mockResolvedValueOnce({ ...row, approval_enabled: true, approval_status: 'approved', approval_request: 'request-1' } as never)
  const first = await harness(); await open(first.wrapper)
  expect(dialog().textContent).not.toContain('修改记录'); expect(dialog().textContent).not.toContain('提交审批')
  first.wrapper.unmount(); wrappers.splice(wrappers.indexOf(first.wrapper), 1)
  vi.mocked(onlineFormLifecycleApi.detail).mockResolvedValue({ ...row, approval_enabled: true, approval_status: 'draft' } as never)
  const second = await harness(); second.auth.user = { ...second.auth.user!, permissions: ['online_form:record_read'] }; await flushPromises()
  await button(second.wrapper, '刷新记录').trigger('click'); await flushPromises(); await open(second.wrapper)
  expect(dialog().textContent).not.toContain('提交审批')
  second.auth.user = { ...second.auth.user!, permissions: ['*'] }; await flushPromises()
  await button(second.wrapper, '刷新记录').trigger('click'); await flushPromises(); await open(second.wrapper)
  let resolve!: (value: never) => void
  vi.mocked(onlineFormLifecycleApi.submitApproval).mockReturnValue(new Promise(r => { resolve = r }))
  await clickDialog('提交审批'); second.auth.user = { ...second.auth.user!, permissions: [] }; await flushPromises()
  resolve({ ...row, approval_enabled: true, approval_status: 'pending', data: { old_title: '旧审批迟到' } } as never); await flushPromises()
  expect(document.body.textContent).not.toContain('旧审批迟到'); expect(document.body.textContent).not.toContain('审批已提交')
})

it('设计器保存可选审批编码，并从有权限表单读取精确租户的流程选项', async () => {
  const form = { id: 'release-1', name: '表单', code: 'expense', status: 'draft', version: 7, definition: oldDefinition, approval_flow_code: 'review' }
  vi.mocked(onlineFormsApi.list).mockResolvedValue({ items: [form], pagination: { total: 1 } } as never)
  vi.mocked(onlineFormLifecycleApi.approvalFlows).mockResolvedValue([{ code: 'review', name: '审核', revision: 2 }])
  vi.mocked(onlineFormsApi.update).mockResolvedValue({ data: { data: form } } as never)
  const { wrapper } = await harness(Designer); await wrapper.get('tbody tr').trigger('click'); await flushPromises()
  const select = wrapper.findAllComponents({ name: 'ElSelect' }).find(item => item.props('modelValue') === 'review')!
  select.vm.$emit('visible-change', true); await flushPromises()
  expect(onlineFormLifecycleApi.approvalFlows).toHaveBeenCalledWith('release-1')
  await button(wrapper, '保存草稿').trigger('click'); await flushPromises()
  expect(onlineFormsApi.update).toHaveBeenCalledWith('release-1', expect.objectContaining({ approval_flow_code: 'review', version: 7 }))
})
