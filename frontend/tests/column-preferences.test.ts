import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { effectScope, ref, nextTick } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { ElTable, type TableInstance } from 'element-plus'
import { normalizeColumns, useColumnPreferences } from '../src/composables/useColumnPreferences'
import BaseTable from '../src/components/common/BaseTable.vue'
import TableColumnSettings from '../src/components/common/TableColumnSettings.vue'
import FieldPolicyEditor from '../src/components/common/FieldPolicyEditor.vue'
import { useAuthStore } from '../src/stores/auth'
import { useTenantStore } from '../src/stores/tenants'

beforeEach(() => { localStorage.clear(); setActivePinia(createPinia()) })
afterEach(() => vi.restoreAllMocks())
const columns = [{ prop: 'name', label: '姓名' }, { prop: 'email', label: '邮箱' }, { prop: 'status', label: '状态' }]

it('偏好只采纳当前登记列，丢弃重复、越权与畸形配置；新增列可见且至少保留一列', () => {
  expect(normalizeColumns([{ prop: 'password', visible: true }, { prop: 'email', visible: false, fixed: 'left' },
    { prop: 'email', visible: true }, { prop: 'name', visible: false, fixed: 'evil' }], columns))
    .toEqual([{ prop: 'email', visible: false, fixed: 'left' }, { prop: 'name', visible: false, fixed: false }, { prop: 'status', visible: true, fixed: false }])
  expect(normalizeColumns([{ prop: 'name', visible: false }], columns.slice(0, 1))[0]?.visible).toBe(true)
})

it('按账号、租户和列表保存，并在身份切换时立即隔离；存储不包含数据或凭据', async () => {
  const scope = effectScope(), key = ref('users'), owner = ref('user-1:tenant-1'), available = ref(columns)
  const prefs = scope.run(() => useColumnPreferences(key, available, owner))!
  prefs.save([{ prop: 'email', visible: true, fixed: 'left' }, { prop: 'name', visible: false, fixed: false }])
  const serialized = JSON.stringify(localStorage)
  expect(serialized).not.toMatch(/token|refresh|secret|rows/)
  owner.value = 'user-1:tenant-2'; await nextTick()
  expect(prefs.layout.value[0]?.prop).toBe('name')
  owner.value = 'user-2:tenant-1'; await nextTick()
  expect(prefs.layout.value[0]?.prop).toBe('name')
  owner.value = 'user-1:tenant-1'; await nextTick()
  expect(prefs.layout.value[0]).toEqual({ prop: 'email', visible: true, fixed: 'left' })
  key.value = 'roles'; await nextTick()
  expect(prefs.layout.value[0]?.prop).toBe('name')
  key.value = 'users'; await nextTick()
  available.value = columns.filter(column => column.prop !== 'email'); await nextTick()
  expect(prefs.layout.value.some(column => column.prop === 'email')).toBe(false)
  owner.value = ''; await nextTick()
  expect(prefs.layout.value[0]?.visible).toBe(true)
  scope.stop()
})

it('存储失败仍可本页设置，损坏JSON安全回退，同列表实例同步设置', async () => {
  const scope = effectScope(), key = ref('users'), owner = ref('user-1'), available = ref(columns)
  const [first, second] = scope.run(() => [useColumnPreferences(key, available, owner), useColumnPreferences(key, available, owner)])!
  first.save([{ prop: 'status', visible: true, fixed: 'right' }])
  expect(second.layout.value[0]?.prop).toBe('status')
  const storedKey = Object.keys(localStorage)[0]!
  localStorage.setItem(storedKey, '{broken')
  window.dispatchEvent(new StorageEvent('storage', { key: storedKey }))
  expect(second.layout.value[0]?.prop).toBe('name')
  expect(second.persistenceUnavailable.value).toBe(true)
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new DOMException('full') })
  first.save([{ prop: 'email', visible: true, fixed: false }])
  expect(first.layout.value[0]?.prop).toBe('email')
  expect(first.persistenceUnavailable.value).toBe(true)
  scope.stop()
})

it('配置入口支持移动、显隐、固定和恢复，保留表格实例/选择/分页，权限变化不能恢复已撤销列', async () => {
  const auth = useAuthStore(); auth.user = { id: 'owner', username: 'owner', email: '', avatar: '' }
  const row = { id: 1, name: '保留行', email: 'private@example.test', status: 'active' }
  const wrapper = mount(BaseTable, { props: { preferenceKey: 'users', data: [row], columns, selectable: true, total: 30, currentPage: 2 } })
  await flushPromises()
  const table = wrapper.getComponent(ElTable), instance = table.vm as unknown as TableInstance
  instance.toggleRowSelection(row, true)
  const settings = wrapper.getComponent(TableColumnSettings)
  settings.vm.$emit('change', [{ prop: 'email', visible: false, fixed: false }, { prop: 'name', visible: true, fixed: 'left' }, { prop: 'status', visible: true, fixed: false }])
  await flushPromises()
  expect(wrapper.getComponent(ElTable).element).toBe(table.element)
  expect(instance.getSelectionRows()).toEqual([row])
  expect(wrapper.findAll('thead th').map(th => th.text()).join(' ')).not.toContain('邮箱')
  expect(wrapper.emitted('update:currentPage')).toBeUndefined()
  expect(wrapper.emitted('update:pageSize')).toBeUndefined()
  await wrapper.setProps({ columns: columns.filter(column => column.prop !== 'email') })
  expect(wrapper.text()).not.toContain('private@example.test')
  useTenantStore().currentId = 'another'; await nextTick()
  auth.user = null; await nextTick()
  expect(wrapper.props('currentPage')).toBe(2)
})

it('列设置的上移/下移、可见性和默认恢复通过真实控件生效', async () => {
  const auth = useAuthStore(); auth.user = { id: 'owner', username: 'owner', email: '', avatar: '' }
  const wrapper = mount(TableColumnSettings, { props: { preferenceKey: 'users', columns }, attachTo: document.body })
  await wrapper.get('button[aria-label="列设置"]').trigger('click'); await flushPromises()
  const popover = document.querySelector('.column-settings')!
  ;(popover.querySelector('button[aria-label="姓名 下移"]') as HTMLButtonElement).click(); await flushPromises()
  expect(wrapper.emitted('change')?.at(-1)?.[0]).toMatchObject([{ prop: 'email' }, { prop: 'name' }, { prop: 'status' }])
  ;(popover.querySelector('[data-column-setting="email"] input[type="checkbox"]') as HTMLInputElement).click(); await flushPromises()
  expect(wrapper.emitted('change')?.at(-1)?.[0]).toEqual(expect.arrayContaining([expect.objectContaining({ prop: 'email', visible: false })]))
  const reset = [...popover.querySelectorAll('button')].find(button => button.textContent?.includes('恢复默认'))!
  reset.click(); await flushPromises()
  expect(wrapper.emitted('change')?.at(-1)?.[0]).toMatchObject([{ prop: 'name', visible: true }, { prop: 'email', visible: true }, { prop: 'status', visible: true }])
  ;(popover.querySelector('button[aria-label="关闭列设置"]') as HTMLButtonElement).click(); await flushPromises()
  expect(document.activeElement).toBe(wrapper.get('button[aria-label="列设置"]').element)
  wrapper.unmount()
})

it('角色字段策略编辑采用显式资源，关闭限制仅移除自身资源且不修改原对象', async () => {
  const original = { orders: { read: ['code'], write: [] }, files: { read: ['id'], write: [] } }
  const wrapper = mount(FieldPolicyEditor, { props: { modelValue: original, resources: { orders: ['code', 'amount'] } } })
  const component = wrapper.findComponent({ name: 'ElSwitch' })
  component.vm.$emit('change', false); await flushPromises()
  expect(wrapper.emitted('update:modelValue')?.[0]?.[0]).toEqual({ files: original.files })
  expect(original.orders.read).toEqual(['code'])
})

it('浏览器禁用存储时列设置仍能挂载并提示，租户初始化不会中断表格', async () => {
  const auth = useAuthStore(); auth.user = { id: 'owner', username: 'owner', email: '', avatar: '' }
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new DOMException('blocked', 'SecurityError') })
  const wrapper = mount(TableColumnSettings, { props: { preferenceKey: 'users', columns }, attachTo: document.body })
  await wrapper.get('button[aria-label="列设置"]').trigger('click'); await flushPromises()
  expect(document.querySelector('.column-settings')?.textContent).toContain('无法保存偏好')
  wrapper.unmount()
})
