import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import { defineComponent } from 'vue'
vi.mock('../src/api/imageProcessing', () => ({ processImage: vi.fn() }))
vi.mock('../src/i18n/uiText', () => ({ uiText: (text: string) => text, registerUiMessages: vi.fn() }))
vi.mock('../src/components', () => ({
  BaseDialog: defineComponent({ name: 'ImageDialogStub', props: ['modelValue', 'beforeClose'], emits: ['confirm'], template: '<div><slot /></div>' }),
  BaseButton: defineComponent({ template: '<button><slot /></button>' }),
}))
import { processImage } from '../src/api/imageProcessing'
import { useAuthStore } from '../src/stores/auth'
import { useModuleStore } from '../src/stores/modules'
import ImageProcessingDialog from '../src/components/files/ImageProcessingDialog.vue'
import type { FileRow } from '../src/api'
const file = { id: 'private', original_name: 'private.png', file_type: 'png', lifecycle_version: 1 } as FileRow
async function harness() {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/files', component: { template: '<div />' } }] })
  await router.push('/files'); await router.isReady()
  const auth = useAuthStore(); auth.applyUser({ id: 'member', username: 'member', email: '', avatar: '', permissions: ['file:process', 'file:download'] })
  useModuleStore().config = { contract_version: 1, preset: 'standard', modules: [{ key: 'files', title: 'files', enabled: true, paths: ['/files'], dependencies: [] }] }
  const wrapper = mount(ImageProcessingDialog, { props: { file, enabled: true }, global: { plugins: [router], stubs: {
    'el-form': defineComponent({ template: '<form><slot /></form>' }),
    'el-form-item': defineComponent({ template: '<div><slot /></div>' }),
    'el-input-number': true, 'el-select': true, 'el-option': true, 'el-button': true,
  } } })
  const confirm = () => wrapper.findComponent({ name: 'ImageDialogStub' }).vm.$emit('confirm')
  return { wrapper, auth, confirm }
}

describe('图片处理结果与设备生命周期', () => {
  beforeEach(() => {
    vi.clearAllMocks(); localStorage.clear(); localStorage.setItem('token', 'image-fixture'); setActivePinia(createPinia())
    URL.createObjectURL = vi.fn(() => 'blob:processed'); URL.revokeObjectURL = vi.fn()
    vi.mocked(processImage).mockResolvedValue(new Blob(['image'], { type: 'image/webp' }))
  })
  it('权限撤销同步关闭窗口，处理中的取消信号被中止，迟到响应不展示', async () => {
    let finish!: (value: Blob) => void
    vi.mocked(processImage).mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const { wrapper, auth, confirm } = await harness()
    confirm(); await flushPromises()
    const signal = vi.mocked(processImage).mock.calls[0]![4]
    auth.applyUser({ ...auth.user!, permissions: ['file:download'] }); await flushPromises()
    expect(signal.aborted).toBe(true)
    finish(new Blob(['late'], { type: 'image/webp' })); await flushPromises()
    expect(wrapper.emitted('close')).toHaveLength(1); expect(wrapper.find('img').exists()).toBe(false)
    wrapper.unmount()
  })
  it('生成只点击一次，关闭释放 URL；更换文件拒绝迟到结果', async () => {
    const { wrapper, confirm } = await harness()
    confirm(); confirm(); await flushPromises()
    expect(processImage).toHaveBeenCalledTimes(1)
    expect(wrapper.find('img').attributes('src')).toBe('blob:processed')
    await wrapper.setProps({ file: null }); await flushPromises()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:processed')
    expect(wrapper.find('img').exists()).toBe(false)
    wrapper.unmount()
  })
  it('请求失败保留草稿可重试，卸载中止请求并拒绝新 Blob URL', async () => {
    const { wrapper, confirm } = await harness()
    vi.mocked(processImage).mockRejectedValueOnce(new Error('version conflict'))
    confirm(); await flushPromises(); expect(wrapper.get('[role="alert"]').text()).toBe('version conflict')
    let finish!: (value: Blob) => void
    vi.mocked(processImage).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    confirm(); await flushPromises()
    const signal = vi.mocked(processImage).mock.calls[1]![4]
    wrapper.unmount(); expect(signal.aborted).toBe(true)
    finish(new Blob(['late'], { type: 'image/webp' })); await flushPromises()
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })
  it('能力关闭及换设备清空表单，不把草稿写入浏览器存储', async () => {
    const { wrapper } = await harness()
    await wrapper.setProps({ enabled: false }); await flushPromises()
    expect(wrapper.emitted('close')).toHaveLength(1)
    expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain('private.png')
    wrapper.unmount()
  })
})
