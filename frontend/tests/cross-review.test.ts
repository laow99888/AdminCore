import { expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { submissionValues } from '@/components/onlineForms/runtime'
import OnlineFileInput from '@/components/onlineForms/OnlineFileInput.vue'
import { filesApi } from '@/api'
import { onlineFormAttachmentsApi } from '@/api/onlineFormAttachments'
import { useAuthStore } from '@/stores/auth'
import { createRouter, createMemoryHistory } from 'vue-router'
import ReportBuilder from '@/views/reports/ReportBuilderView.vue'
import { reportsApi } from '@/api'

it('F5: explicit clearing of an optional default must survive submission normalization', () => {
  const fields = [{ key: 'note', label: '备注', type: 'text' as const, required: false, default: '默认备注', max_length: 100 }]
  // Omitting note causes the backend to restore its default; the explicit blank must survive.
  expect(submissionValues(fields, { note: '' })).toHaveProperty('note', '')
})

it('F7: retrying a failed empty attachment search must retry the options query', async () => {
  const pinia = createPinia(); setActivePinia(pinia)
  const auth = useAuthStore(); auth.user = { id: 'audit-user', username: 'audit', permissions: ['*'] } as never
  auth.token = 'synthetic-audit-token'
  const choices = vi.spyOn(onlineFormAttachmentsApi, 'choices')
    .mockRejectedValueOnce(new Error('synthetic network failure'))
    .mockResolvedValue({ items: [], selected: null, has_more: false })
  const wrapper = mount(OnlineFileInput, { props: { id: 'attachment', label: '附件', context: { code: 'audit', formId: 'audit-form' } }, global: { plugins: [pinia, ElementPlus] } })
  wrapper.findComponent({ name: 'ElSelect' }).vm.$emit('visible-change', true)
  await flushPromises()
  await wrapper.findAll('button').find(item => item.text() === '重试')!.trigger('click')
  await flushPromises()
  try { expect(choices.mock.calls[1][2].resolve).toBe(false) } finally { wrapper.unmount(); vi.restoreAllMocks() }
})

it('F8: saved report selection must provide keyboard activation', async () => {
  const pinia = createPinia(); setActivePinia(pinia)
  const auth = useAuthStore(); auth.user = { id: 'audit-user', username: 'audit', permissions: ['*'], is_staff: true } as never
  auth.token = 'synthetic-audit-token'
  const row = { id: 'audit-report', name: '审查草稿', code: 'audit', kind: 'report', status: 'draft', version: 1,
    definition: { data_source: 'tasks', chart_type: 'table', dimensions: [], metrics: [{ key: 'm_count', label: '计数', field: 'id', aggregation: 'count' }], filters: [], limit: 100 }, created_at: '', updated_at: '' }
  vi.spyOn(reportsApi, 'catalog').mockResolvedValue([{ key: 'tasks', label: '任务', dimensions: ['status'], metrics: ['id'], filters: ['status'] }])
  vi.spyOn(reportsApi, 'list').mockResolvedValue({ items: [row], pagination: { page: 1, page_size: 20, total: 1, total_pages: 1 } } as never)
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/reports', component: { template: '<div />' } }] })
  await router.push('/reports')
  const wrapper = mount(ReportBuilder, { global: { plugins: [pinia, router, ElementPlus], stubs: { AppLayout: { template: '<main><slot /></main>' }, ReportViewer: true } } })
  await flushPromises()
  const reportRow = wrapper.get('tbody tr')
  const selectButton = reportRow.findAll('button').find(button => button.text() === row.name)
  try {
    expect(selectButton, 'report has a native keyboard-operable selection button').toBeDefined()
    await selectButton!.trigger('click'); await flushPromises()
    expect((wrapper.get('input[maxlength="120"]').element as HTMLInputElement).value).toBe(row.name)
  } finally { wrapper.unmount(); vi.restoreAllMocks() }

})

it('F6: searching attachment choices during an upload must release upload busy state', async () => {
  const pinia = createPinia(); setActivePinia(pinia)
  const auth = useAuthStore(); auth.user = { id: 'audit-user', username: 'audit', permissions: ['*'] } as never
  auth.token = 'synthetic-audit-token'
  let finishUpload!: (value: unknown) => void
  vi.spyOn(filesApi, 'upload').mockImplementation(() => new Promise(resolve => { finishUpload = resolve as never }))
  vi.spyOn(onlineFormAttachmentsApi, 'choices').mockResolvedValue({ items: [], selected: null, has_more: false })
  const wrapper = mount(OnlineFileInput, { props: { id: 'attachment', label: '附件', context: { code: 'audit', formId: 'audit-form' } }, global: { plugins: [pinia, ElementPlus] } })
  const file = wrapper.find('input[type=file]')
  Object.defineProperty(file.element, 'files', { value: [new File(['fixture'], 'audit.txt')] })
  await file.trigger('change')
  expect(wrapper.text()).toContain('上传附件')
  wrapper.findComponent({ name: 'ElSelect' }).vm.$emit('visible-change', true)
  await flushPromises()
  finishUpload({ data: { data: { id: 'uploaded-file' } } })
  await flushPromises()
  const button = wrapper.findAll('button').find(item => item.text().includes('上传附件'))!
  try { expect(button.element.disabled).toBe(false) } finally { wrapper.unmount(); vi.restoreAllMocks() }
})

import sharedValues from '../../contracts/online-form-values.json'
import type { OnlineFormField } from '@/api'
it.each(sharedValues.cases)('共享协议夹具：$name', row => {
  expect(submissionValues(sharedValues.definition.fields as OnlineFormField[], row.input)).toEqual(row.submission)
})
