import { expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { useAuthStore } from '../src/stores/auth'
import { filesApi } from '../src/api'
import Files from '../src/views/files/FileListView.vue'
vi.mock('../src/api', () => ({filesApi:{list:vi.fn(),remove:vi.fn()}}))
vi.mock('../src/api/officePreview', () => ({isOfficeFormat:()=>false,officePreviewConfig:async()=>false}))
vi.mock('../src/api/imageProcessing', () => ({canProcessImage:()=>false,imageProcessingConfig:async()=>({enabled:false})}))
vi.mock('../src/stores/modules', () => ({useModuleStore:()=>({config:{contract_version:1,modules:[]},enabled:()=>false,pathEnabled:()=>true})}))
const Layout=defineComponent({template:'<div><slot name="header"/><slot/></div>'})
const Table=defineComponent({props:['data'],template:'<div><slot v-for="row in data" name="actions" :row="row"/></div>'})
it('旧身份离开后删除确认不能发出旧操作',async()=>{
  localStorage.clear();const pinia=createPinia(),auth=useAuthStore(pinia)
  auth.token='old-token';auth.user={id:'old-user',username:'old',email:'',avatar:'',permissions:['*']}
  vi.mocked(filesApi.list).mockResolvedValue({items:[{id:'old-file',original_name:'old.txt',file_type:'txt',size:1}],pagination:{page:1,page_size:10,total:1,total_pages:1}} as never)
  vi.mocked(filesApi.remove).mockResolvedValue({} as never)
  const router=createRouter({history:createMemoryHistory(),routes:[{path:'/files',component:Layout}]});await router.push('/files')
  const wrapper=mount(Files,{global:{plugins:[pinia,router,ElementPlus],stubs:{AppLayout:Layout,BaseCard:Layout,BaseTable:Table,FilePreviewDialog:true,FileReferencesDialog:true,FileVersionsDialog:true,FileCapacityPanel:true,FileLibraryToolbar:true,ImageProcessingDialog:true,DataExportButton:true,LocalExportButton:true,PrintTableButton:true}}})
  await flushPromises();let confirm!:()=>void
  vi.spyOn(ElMessageBox,'confirm').mockImplementation(()=>new Promise(resolve=>{confirm=()=>resolve('confirm' as never)}))
  await wrapper.findAll('button').find(button=>button.text()==='删除')!.trigger('click')
  auth.token='new-token';auth.user={id:'new-user',username:'new',email:'',avatar:'',permissions:['*']};wrapper.unmount()
  expect(filesApi.remove).not.toHaveBeenCalled()
  confirm();await flushPromises()
  expect(filesApi.remove).not.toHaveBeenCalled();vi.restoreAllMocks()
})
