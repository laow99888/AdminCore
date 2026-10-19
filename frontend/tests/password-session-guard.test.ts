import { describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ElForm } from 'element-plus'
import { useAuthStore } from '../src/stores/auth'
import authApi from '../src/api/auth'
import ChangePasswordForm from '../src/components/auth/ChangePasswordForm.vue'
vi.mock('../src/api/auth', () => ({default:{changePassword:vi.fn()}}))
describe('改密响应归属隔离', () => {
  it('旧改密响应不能清除新登录身份', async () => {
    localStorage.clear(); localStorage.setItem('token','old-session-fixture');localStorage.setItem('refreshToken','old-refresh')
    const pinia=createPinia(),auth=useAuthStore(pinia)
    auth.applyUser({id:'old-user', username:'old',email:'',avatar:'',permissions:[]})
    const router=createRouter({history:createMemoryHistory(),routes:[{path:'/settings',component:{template:'<div />'}},{path:'/login',component:{template:'<div />'}}]})
    await router.push('/settings')
    const wrapper=mount(ChangePasswordForm,{global:{plugins:[pinia,router]}})
    vi.spyOn(wrapper.getComponent(ElForm).vm.$.exposed!,'validate').mockResolvedValue(true)
    await wrapper.get('input[autocomplete="current-password"]').setValue('OldFixture123!')
    for(const input of wrapper.findAll('input[autocomplete="new-password"]')) await input.setValue('NewFixture123!')
    let complete!:()=>void
    vi.mocked(authApi.changePassword).mockImplementation(()=>new Promise<void>(resolve=>{complete=resolve}))
    await wrapper.get('form').trigger('submit');await flushPromises();expect(authApi.changePassword).toHaveBeenCalledOnce()
    localStorage.setItem('token','new-session-fixture');localStorage.setItem('refreshToken','new-refresh')
    auth.token='new-session-fixture';auth.applyUser({id:'new-user',username:'new',email:'',avatar:'',permissions:[]})
    expect(auth.user?.id).toBe('new-user')
    complete();await flushPromises()
    expect(auth.user?.id).toBe('new-user');expect(localStorage.getItem('token')).toBe('new-session-fixture');wrapper.unmount()
  })
})
