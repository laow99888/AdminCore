import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import ElementPlus, { ElSelect } from 'element-plus'
import { createPinia } from 'pinia'
import { useAuthStore } from '../src/stores/auth'
import { useTenantStore } from '../src/stores/tenants'
import { filesApi } from '../src/api'
import { onlineFormAttachmentsApi } from '../src/api/onlineFormAttachments'
import FileInput from '../src/components/onlineForms/OnlineFileInput.vue'
import Renderer from '../src/components/onlineForms/OnlineFormRenderer.vue'
import FieldDesigner from '../src/components/onlineForms/FieldDesigner.vue'
import ConditionEditor from '../src/components/onlineForms/ConditionEditor.vue'

vi.mock('../src/api', () => ({ filesApi: { upload: vi.fn(), downloadUrl: vi.fn() }, downloadFile: vi.fn() }))
vi.mock('../src/api/onlineFormAttachments', () => ({ onlineFormAttachmentsApi: { choices: vi.fn() } }))
vi.mock('../src/components/files/FilePreviewDialog.vue', () => ({ default: defineComponent({ template: '<div>preview</div>' }) }))
const wrappers: VueWrapper[] = []
const attachment = { id: 'ef23a35e-6dc1-4e4f-bcb0-cf69c8f21a12', original_name: '租户 A 私密合同.pdf', size: 5, file_type: 'pdf' }
const context = { code: 'expenses', recordId: 'record-1' }
const result = (selected: typeof attachment | null = attachment) => ({ selected, items: [], has_more: false })
beforeEach(() => { vi.resetAllMocks(); localStorage.clear(); vi.mocked(onlineFormAttachmentsApi.choices).mockResolvedValue(result()) })
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()); document.body.innerHTML = ''; localStorage.clear() })
function token(sid = 'session', session_version = 1, jti = 'initial') { return `header.${btoa(JSON.stringify({ sid, user_id: 'owner', session_version, jti }))}.signature` }
async function harness(props: Record<string, unknown> = {}, access = 'test') {
  const pinia = createPinia(), auth = useAuthStore(pinia), tenants = useTenantStore(pinia)
  auth.token = access; auth.user = { id: 'owner', username: 'owner', email: '', avatar: '', permissions: ['file:read', 'file:download', 'file:upload'] }
  const wrapper = mount(FileInput, { props: { id: 'proof', label: '合同附件', context, ...props }, attachTo: document.body, global: { plugins: [pinia, ElementPlus] } })
  wrappers.push(wrapper); await flushPromises(); return { wrapper, auth, tenants }
}
it('未保存的设计器附件不发送查询，控件与上传关闭并解释原因', async () => {
  const { wrapper } = await harness({ context: undefined })
  expect(wrapper.text()).toContain('保存表单后可选择附件')
  expect(wrapper.get('input[role="combobox"]').attributes('disabled')).toBeDefined()
  expect(wrapper.text()).not.toContain('上传附件'); expect(onlineFormAttachmentsApi.choices).not.toHaveBeenCalled()
})
it('历史只读通过记录和具体明细字段解析；不搜索或上传', async () => {
  const { wrapper } = await harness({ disabled: true, id: 'lines.0.proof', modelValue: attachment.id })
  expect(onlineFormAttachmentsApi.choices).toHaveBeenLastCalledWith(context, 'lines.0.proof', expect.objectContaining({ selected: attachment.id, resolve: true }), expect.any(AbortSignal))
  expect(wrapper.text()).toContain(attachment.original_name)
  expect(wrapper.find('input').exists()).toBe(false)
  expect(wrapper.text()).not.toContain('上传附件'); expect(wrapper.text()).toContain('下载')
})
it('编辑器迟到解析会刷新已选附件标签，撤权后移除旧文件名', async () => {
  let resolve!: (value: ReturnType<typeof result>) => void
  vi.mocked(onlineFormAttachmentsApi.choices).mockReturnValueOnce(new Promise(r => { resolve = r }))
  const { wrapper, tenants } = await harness({ modelValue: attachment.id })
  expect(wrapper.get('.el-select__placeholder').text()).toBe('附件不可用或无权访问')
  resolve(result()); await flushPromises()
  expect(wrapper.get('.el-select__placeholder').text()).toBe(attachment.original_name)
  vi.mocked(onlineFormAttachmentsApi.choices).mockResolvedValue(result(null))
  tenants.currentId = 'tenant-b'; await flushPromises()
  expect(wrapper.get('.el-select__placeholder').text()).toBe('附件不可用或无权访问')
  expect(wrapper.text()).not.toContain(attachment.original_name)
})
it('失去文件权限会同步移除文件名、预览和下载，迟到解析不能恢复', async () => {
  let resolve!: (value: ReturnType<typeof result>) => void
  vi.mocked(onlineFormAttachmentsApi.choices).mockReturnValue(new Promise(r => { resolve = r }))
  const { wrapper, auth } = await harness({ disabled: true, modelValue: attachment.id })
  auth.user = { ...auth.user!, permissions: [] }; await flushPromises()
  resolve(result()); await flushPromises()
  expect(wrapper.text()).not.toContain(attachment.original_name); expect(wrapper.text()).toContain('附件不可用或无权访问')
  expect(wrapper.text()).not.toContain('下载'); expect(wrapper.text()).not.toContain('预览')
})
it('切换租户时立即清空解析结果且旧响应不会恢复文件名', async () => {
  const { wrapper, tenants } = await harness({ disabled: true, modelValue: attachment.id })
  expect(wrapper.text()).toContain(attachment.original_name)
  let resolve!: (value: ReturnType<typeof result>) => void
  vi.mocked(onlineFormAttachmentsApi.choices).mockReturnValueOnce(new Promise(r => { resolve = r })).mockResolvedValue(result(null))
  await wrapper.setProps({ id: 'lines.0.proof' })
  tenants.currentId = 'tenant-b'; await flushPromises(); resolve(result()); await flushPromises()
  expect(wrapper.text()).not.toContain(attachment.original_name); expect(wrapper.text()).toContain('附件不可用或无权访问')
})
it('搜索错误有可恢复状态，下一次成功替换选项而不显示失效名称', async () => {
  const { wrapper } = await harness()
  vi.mocked(onlineFormAttachmentsApi.choices).mockRejectedValueOnce(new Error('无法查询')).mockResolvedValueOnce({ ...result(null), items: [attachment] })
  wrapper.getComponent(ElSelect).vm.$emit('visible-change', true); await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('重试')
  wrapper.getComponent(ElSelect).vm.$emit('visible-change', true); await flushPromises()
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  expect(wrapper.getComponent(ElSelect).findAllComponents({ name: 'ElOption' }).map(item => item.props('label'))).toContain(attachment.original_name)
})
it('上传先复核目标表单附件 ACL，再更新字段；租户切换使迟到上传作废', async () => {
  let resolve!: (value: never) => void
  vi.mocked(filesApi.upload).mockResolvedValueOnce({ data: { data: attachment } } as never).mockReturnValueOnce(new Promise(r => { resolve = r }))
  const { wrapper, tenants } = await harness()
  const input = wrapper.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['test'], 'contract.pdf')] })
  await input.trigger('change'); await flushPromises()
  expect(onlineFormAttachmentsApi.choices).toHaveBeenLastCalledWith(context, 'proof', { selected: attachment.id, resolve: true })
  expect(wrapper.emitted('update:modelValue')).toEqual([[attachment.id]])
  await input.trigger('change'); tenants.currentId = 'tenant-b'; await flushPromises()
  resolve({ data: { data: attachment } } as never); await flushPromises()
  expect(wrapper.emitted('update:modelValue')).toHaveLength(1)
})
it('同会话令牌轮换保留附件名称与待完成上传，不重新解析或丢弃成功结果', async () => {
  let resolve!: (value: Awaited<ReturnType<typeof filesApi.upload>>) => void
  vi.mocked(filesApi.upload).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const { wrapper, auth } = await harness({ modelValue: attachment.id }, token())
  const input = wrapper.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['test'], 'contract.pdf')] })
  await input.trigger('change')
  const signal = vi.mocked(onlineFormAttachmentsApi.choices).mock.calls[0]![3]!
  auth.token = token('session', 1, 'rotated'); await flushPromises()
  expect(signal.aborted).toBe(false)
  expect(onlineFormAttachmentsApi.choices).toHaveBeenCalledTimes(1)
  expect(wrapper.get('.el-select__placeholder').text()).toBe(attachment.original_name)
  resolve({ data: { data: attachment } } as Awaited<ReturnType<typeof filesApi.upload>>); await flushPromises()
  expect(wrapper.emitted('update:modelValue')).toEqual([[attachment.id]])
})
it.each(['sid', 'version'] as const)('%s变化撤销附件解析并拒绝迟到上传', async change => {
  let resolve!: (value: Awaited<ReturnType<typeof filesApi.upload>>) => void
  vi.mocked(filesApi.upload).mockImplementationOnce(() => new Promise(done => { resolve = done }))
  const { wrapper, auth } = await harness({ modelValue: attachment.id }, token())
  const input = wrapper.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', { configurable: true, value: [new File(['test'], 'contract.pdf')] })
  await input.trigger('change')
  const signal = vi.mocked(onlineFormAttachmentsApi.choices).mock.calls[0]![3]!
  vi.mocked(onlineFormAttachmentsApi.choices).mockResolvedValue(result(null))
  auth.token = change === 'sid' ? token('other') : token('session', 2)
  await flushPromises(); resolve({ data: { data: attachment } } as Awaited<ReturnType<typeof filesApi.upload>>); await flushPromises()
  expect(signal.aborted).toBe(true)
  expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  expect(wrapper.get('.el-select__placeholder').text()).toBe('附件不可用或无权访问')
})
it('父表单禁用状态传到主表及明细附件，不被默认 disabled=false 覆盖', async () => {
  const pinia = createPinia(), auth = useAuthStore(pinia)
  auth.user = { id: 'owner', username: 'owner', email: '', avatar: '', permissions: ['file:read', 'file:upload'] }
  const wrapper = mount(Renderer, { props: { disabled: true, attachmentContext: context, modelValue: { proof: attachment.id, lines: [{ proof: attachment.id }] }, definition: { schema_version: 2, fields: [
    { key: 'proof', label: '主附件', type: 'file', required: false },
    { key: 'lines', label: '明细', type: 'detail', required: false, fields: [{ key: 'proof', label: '明细附件', type: 'file', required: false }] },
  ] } }, global: { plugins: [pinia, ElementPlus] } })
  wrappers.push(wrapper); await flushPromises()
  expect(wrapper.findAllComponents(FileInput)).toHaveLength(2)
  expect(wrapper.findAll('input[type="file"]')).toHaveLength(0)
  expect(onlineFormAttachmentsApi.choices).toHaveBeenCalledWith(context, 'lines.0.proof', expect.objectContaining({ resolve: true }), expect.any(AbortSignal))
})
it('附件设计器隐藏默认值，条件编辑只提供空和非空操作', async () => {
  const fields = [{ key: 'proof', label: '附件', type: 'file' as const, required: false }]
  const designer = mount(FieldDesigner, { props: { modelValue: fields, sections: [] }, global: { plugins: [ElementPlus] } }); wrappers.push(designer)
  expect(designer.find('.default-row').exists()).toBe(false)
  const condition = mount(ConditionEditor, { props: { fields, id: 'test', modelValue: [{ field: 'proof', op: 'not_empty' }] }, global: { plugins: [ElementPlus] } }); wrappers.push(condition)
  expect(condition.findAllComponents(ElSelect)[1]!.findAllComponents({ name: 'ElOption' }).map(row => row.props('value'))).toEqual(['empty', 'not_empty'])
})
