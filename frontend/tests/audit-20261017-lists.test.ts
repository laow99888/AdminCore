import { beforeEach, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { useAuthStore } from '../src/stores/auth'
import { filesApi, rolesApi, permissionsApi } from '../src/api'
import Files from '../src/views/files/FileListView.vue'
import Roles from '../src/views/system/RoleListView.vue'

vi.mock('../src/i18n/uiText', async (importOriginal) => ({ ...await importOriginal<object>(), uiText: (value: string) => value }))
vi.mock('../src/api', () => ({ filesApi: { list: vi.fn(), remove: vi.fn() }, rolesApi: { list: vi.fn(), remove: vi.fn() }, permissionsApi: { list: vi.fn() } }))
vi.mock('../src/api/officePreview', () => ({ isOfficeFormat: () => false, officePreviewConfig: async () => false }))
vi.mock('../src/api/imageProcessing', () => ({ canProcessImage: () => false, imageProcessingConfig: async () => ({ enabled: false }) }))
vi.mock('../src/stores/modules', () => ({ useModuleStore: () => ({ enabled: () => true, config: {} }) }))
const Table = defineComponent({ name: 'BaseTable', props: ['data', 'currentPage', 'total', 'loading'], emits: ['update:currentPage'], template: '<div><slot v-for="row in data" name="actions" :row="row" /></div>' })
const Layout = defineComponent({ template: '<main><slot name="header" /><slot /></main>' })
const row = { id: 'row', name: 'role', original_name: 'file.txt', file_type: 'txt', size: 1, permissions: [], version: 1 }
const page = (id: string) => ({ items: [{ ...row, id }], pagination: { page: 1, page_size: 10, total: 30, total_pages: 3 } })
function pending<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(done => { resolve = done }); return { promise, resolve } }
beforeEach(() => { vi.resetAllMocks(); localStorage.clear(); vi.mocked(permissionsApi.list).mockResolvedValue({ items: [], pagination: { total_pages: 1 } } as never) })

for (const [name, component, api] of [['文件', Files, filesApi], ['角色', Roles, rolesApi]] as const) {
  async function setup() {
    const pinia = createPinia(), auth = useAuthStore(pinia)
    auth.token = 'isolated-list'; auth.user = { id: 'owner', username: 'owner', email: '', avatar: '', is_staff: true, permissions: ['*'] }
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/list', component: Layout }] }); await router.push('/list')
    const wrapper = mount(component, { global: { plugins: [pinia, router, ElementPlus], stubs: {
      AppLayout: Layout, BaseCard: Layout, BaseTable: Table, BaseDialog: true, FilePreviewDialog: true, ImageProcessingDialog: true,
      DataImportButton: true, DataExportButton: true, LocalExportButton: true, PrintTableButton: true, FileLibraryToolbar: true,
    } } })
    return { wrapper, auth, table: wrapper.getComponent(Table) }
  }
  it(`${name}：乱序旧响应和换身份后的响应不能覆盖当前列表`, async () => {
    const first = pending<ReturnType<typeof page>>(), second = pending<ReturnType<typeof page>>()
    vi.mocked(api.list).mockReturnValueOnce(first.promise as never).mockReturnValueOnce(second.promise as never)
    const { wrapper, auth, table } = await setup()
    table.vm.$emit('update:currentPage', 2)
    second.resolve(page('new')); await flushPromises(); expect(table.props('data')[0].id).toBe('new')
    first.resolve(page('old')); await flushPromises(); expect(table.props('data')[0].id).toBe('new')
    const late = pending<ReturnType<typeof page>>(); vi.mocked(api.list).mockReturnValueOnce(late.promise as never)
    table.vm.$emit('update:currentPage', 3)
    auth.user = { ...auth.user!, id: 'replacement' }
    late.resolve(page('private-old')); await flushPromises()
    expect(table.props('data')).toEqual([]); expect(table.props('total')).toBe(0)
    wrapper.unmount()
  })
  it(`${name}：删除末页最后一条回到前页；并发删除造成404仅回退一次`, async () => {
    vi.mocked(api.list).mockResolvedValue(page('row') as never)
    vi.mocked(api.remove).mockResolvedValue({} as never)
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    const { wrapper, table } = await setup(); await flushPromises()
    table.vm.$emit('update:currentPage', 3); await flushPromises()
    await wrapper.findAll('button').find(item => item.text() === '删除')!.trigger('click'); await flushPromises()
    expect(api.list).toHaveBeenLastCalledWith({ page: 2, page_size: 10 })
    vi.mocked(api.list).mockRejectedValueOnce({ response: { status: 404 } }).mockResolvedValueOnce(page('remaining') as never)
    table.vm.$emit('update:currentPage', 3); await flushPromises()
    expect(api.list).toHaveBeenLastCalledWith({ page: 1, page_size: 10 })
    expect(table.props('data')[0].id).toBe('remaining')
    wrapper.unmount()
  })
}
