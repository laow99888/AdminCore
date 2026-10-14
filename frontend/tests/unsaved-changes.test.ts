import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent, h, reactive, ref } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { ElForm, ElMessageBox } from 'element-plus'
import ChangePasswordForm from '../src/components/auth/ChangePasswordForm.vue'
import authApi from '../src/api/auth'
import BaseDialog from '../src/components/common/BaseDialog.vue'
import BaseForm from '../src/components/common/BaseForm.vue'
import { confirmPendingForms, useUnsavedChanges } from '../src/composables/useUnsavedChanges'
import { useAuthStore } from '../src/stores/auth'

vi.mock('../src/api/auth', () => ({ default: { changePassword: vi.fn() } }))

afterEach(() => { vi.restoreAllMocks(); localStorage.clear() })

async function harness(two = false) {
  localStorage.setItem('token', 'isolated-unit-fixture')
  const pinia = createPinia(), auth = useAuthStore(pinia)
  auth.applyUser({ id: 'fixture', username: 'fixture', email: '', avatar: '', permissions: ['edit'] })
  const form = reactive({ name: '', nested: { ids: ['a'] } }), active = ref(false), busy = ref(false)
  let guard!: ReturnType<typeof useUnsavedChanges>
  let second!: ReturnType<typeof useUnsavedChanges>
  const other = reactive({ name: '' })
  const editor = defineComponent({ setup() {
    guard = useUnsavedChanges({ source: () => form, active: () => active.value, busy: () => busy.value,
      canEdit: () => auth.can('edit'), clear: () => { active.value = false; form.name = ''; form.nested.ids = [] } })
    if (two) second = useUnsavedChanges({ source: () => other, busy: () => busy.value, clear: () => { other.name = '' } })
    return () => h('div', form.name)
  } })
  const blank = defineComponent({ render: () => h('div', 'blank') })
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/edit', component: editor }, { path: '/other', component: blank }, { path: '/login', component: blank },
    { path: '/403', component: blank }, { path: '/change-password', component: blank },
  ] })
  await router.push('/edit')
  const wrapper = mount(defineComponent({ render: () => h(RouterView) }), { global: { plugins: [pinia, router] } })
  await flushPromises()
  return { pinia, auth, form, active, busy, guard, second, other, router, wrapper }
}

describe('统一草稿保护', () => {
  it('打开以加载值建立基线；嵌套修改可识别，恢复原值不再提示', async () => {
    const { form, active, guard } = await harness()
    form.name = 'loaded'; active.value = true
    expect(guard.dirty.value).toBe(false)
    form.nested.ids.push('b'); expect(guard.dirty.value).toBe(true)
    form.nested.ids.pop(); expect(guard.dirty.value).toBe(false)
    form.name = 'saved'; guard.markClean(); expect(guard.dirty.value).toBe(false)
    const confirm = vi.spyOn(ElMessageBox, 'confirm')
    expect(await confirmPendingForms()).toBe(true); expect(confirm).not.toHaveBeenCalled()
  })
  it('路由和页签使用的正常跳转取消后保留输入，确认后离开并清敏感字段', async () => {
    const { form, active, router } = await harness()
    active.value = true; form.name = 'private draft'
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockRejectedValueOnce('cancel').mockResolvedValueOnce(undefined as never)
    await router.push('/other'); expect(router.currentRoute.value.path).toBe('/edit'); expect(form.name).toBe('private draft')
    await router.push('/other'); await flushPromises()
    expect(router.currentRoute.value.path).toBe('/other'); expect(form.name).toBe('')
    expect(confirm).toHaveBeenCalledTimes(2)
  })
  it('多个资料/改密草稿及并发离开检查只有一次确认', async () => {
    const { form, other, active } = await harness(true)
    active.value = true; form.name = 'one'; other.name = 'two'
    let finish!: () => void
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockImplementation(() => new Promise(resolve => { finish = () => resolve(undefined as never) }))
    const first = confirmPendingForms(), second = confirmPendingForms()
    expect(confirm).toHaveBeenCalledTimes(1)
    finish(); expect(await first).toBe(true); expect(await second).toBe(true)
  })
  it('忙碌同步阻止关闭和跳转，不弹额外提示；finally 恢复后正常确认', async () => {
    const { form, active, busy, guard, router } = await harness()
    active.value = true; form.name = 'draft'; busy.value = true
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue('cancel')
    expect(await guard.confirmDiscard()).toBe(false)
    await router.push('/other'); expect(router.currentRoute.value.path).toBe('/edit'); expect(confirm).not.toHaveBeenCalled()
    busy.value = false; expect(await guard.confirmDiscard()).toBe(false); expect(confirm).toHaveBeenCalledTimes(1)
    expect(form.name).toBe('draft')
  })
  it.each(['/login', '/403', '/change-password'])('安全跳转 %s 绕过忙碌守卫并清字段', async path => {
    const { form, active, busy, router } = await harness()
    active.value = true; form.name = 'private'; busy.value = true
    const confirm = vi.spyOn(ElMessageBox, 'confirm')
    await router.push(path); await flushPromises()
    expect(router.currentRoute.value.path).toBe(path); expect(form.name).toBe(''); expect(confirm).not.toHaveBeenCalled()
  })
  it('丢失编辑权限立即清理，关闭提示不能阻止撤权', async () => {
    const { auth, form, active, guard } = await harness()
    active.value = true; form.name = 'private'
    auth.applyUser({ id: 'fixture', username: 'fixture', email: '', avatar: '', permissions: [] })
    expect(form.name).toBe(''); expect(active.value).toBe(false); expect(guard.dirty.value).toBe(false)
    expect(guard.isCurrent()).toBe(false)
  })
  it('切换为另一有权限账户同样清理旧草稿，不能应用旧请求结果', async () => {
    const { auth, form, active, guard } = await harness()
    active.value = true; form.name = 'old owner draft'
    auth.applyUser({ id: 'another-account', username: 'other', email: '', avatar: '', permissions: ['edit'] })
    expect(form.name).toBe(''); expect(guard.isCurrent()).toBe(false)
  })
  it('关闭窗口只拦截真正草稿；关闭或卸载后移除事件且不写存储', async () => {
    const { form, active, wrapper } = await harness()
    const write = vi.spyOn(Storage.prototype, 'setItem')
    active.value = true
    let event = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(event); expect(event.defaultPrevented).toBe(false)
    form.name = 'private'; event = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(event); expect(event.defaultPrevented).toBe(true)
    active.value = false; expect(form.name).toBe('')
    wrapper.unmount(); event = new Event('beforeunload', { cancelable: true }); window.dispatchEvent(event); expect(event.defaultPrevented).toBe(false)
    expect(write).not.toHaveBeenCalled()
  })
})

describe('基础组件关闭与校验锁', () => {
  it.each(['clear', 'switch'])('异步改密校验中 %s 会话，不发送请求且清掉密码', async action => {
    const { auth, pinia, router } = await harness()
    const wrapper = mount(ChangePasswordForm, { global: { plugins: [pinia, router] } })
    await wrapper.get('input[autocomplete="current-password"]').setValue('FixtureOld123!')
    const newInputs = wrapper.findAll('input[autocomplete="new-password"]')
    await newInputs[0]!.setValue('FixtureNew123!'); await newInputs[1]!.setValue('FixtureNew123!')
    let complete!: (value: boolean) => void
    vi.spyOn(wrapper.getComponent(ElForm).vm.$.exposed!, 'validate').mockImplementation(() => new Promise(resolve => { complete = resolve }))
    await wrapper.get('form').trigger('submit')
    if (action === 'clear') auth.clearSession()
    else auth.applyUser({ id: 'new-owner', username: 'other', email: '', avatar: '', permissions: ['edit'] })
    complete(true); await flushPromises()
    expect(authApi.changePassword).not.toHaveBeenCalled()
    expect(wrapper.findAll('input').every(input => (input.element as HTMLInputElement).value === '')).toBe(true)
    expect(wrapper.get('input[autocomplete="current-password"]').attributes('disabled')).toBeUndefined()
  })
  it('取消和 X 均等待草稿确认，拒绝保留弹窗；成功批准才关闭', async () => {
    const beforeClose = vi.fn().mockResolvedValue(false)
    const wrapper = mount(BaseDialog, { props: { modelValue: true, beforeClose }, global: { stubs: { teleport: true } } })
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '取消')!.trigger('click'); await flushPromises()
    await wrapper.get('.el-dialog__headerbtn').trigger('click'); await flushPromises()
    expect(beforeClose).toHaveBeenCalledTimes(2); expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    beforeClose.mockResolvedValue(true)
    await wrapper.findAll('button').find(button => button.text() === '取消')!.trigger('click'); await flushPromises()
    expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
  })
  it('加载期间不能取消/X，且兼容原 callback before-close', async () => {
    const beforeClose = vi.fn((done: () => void) => done())
    const wrapper = mount(BaseDialog, { props: { modelValue: true, loading: true, beforeClose }, global: { stubs: { teleport: true } } })
    await flushPromises()
    expect(wrapper.findAll('button').find(button => button.text() === '取消')!.attributes('disabled')).toBeDefined()
    await wrapper.get('.el-dialog__headerbtn').trigger('click'); await flushPromises(); expect(beforeClose).not.toHaveBeenCalled()
    await wrapper.setProps({ loading: false }); await wrapper.findAll('button').find(button => button.text() === '取消')!.trigger('click'); await flushPromises()
    expect(beforeClose).toHaveBeenCalledOnce(); expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
  })
  it('异步校验开始即锁输入/重置，重复 submit 只有一次校验与一次提交', async () => {
    let complete!: () => void
    const validate = vi.fn((_rule, _value, done: (error?: Error) => void) => { complete = () => done() })
    const wrapper = mount(BaseForm, { props: { modelValue: { name: 'fixture' }, fields: [{ prop: 'name', label: 'Name', type: 'text' }], rules: { name: [{ validator: validate }] } } })
    await wrapper.get('form').trigger('submit')
    await wrapper.get('form').trigger('submit')
    expect(validate).toHaveBeenCalledOnce(); expect(wrapper.get('input').attributes('disabled')).toBeDefined()
    await wrapper.get('button:last-child').trigger('click'); expect(wrapper.emitted('update:modelValue')).toBeUndefined()
    complete(); await flushPromises(); expect(wrapper.emitted('submit')).toHaveLength(1)
    expect(wrapper.get('input').attributes('disabled')).toBeUndefined()
  })
})
