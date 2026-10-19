import { expect, it } from 'vitest'
import { KeepAlive, defineComponent, h, ref } from 'vue'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { useActionGuard } from '../src/composables/useActionGuard'

it('KeepAlive 离开页面立即作废旧操作，回来也不能复活旧确认', async () => {
  setActivePinia(createPinia())
  const visible = ref(true)
  let begin!: ReturnType<typeof useActionGuard>
  const Probe = defineComponent({ setup() { begin = useActionGuard(); return () => h('div', 'guard') } })
  const Host = defineComponent({ setup: () => () => h(KeepAlive, null, { default: () => visible.value ? h(Probe) : h('span') }) })
  const wrapper = mount(Host)
  await flushPromises()
  const old = begin()
  expect(old()).toBe(true)
  visible.value = false
  await flushPromises()
  expect(old()).toBe(false)
  visible.value = true
  await flushPromises()
  expect(old()).toBe(false)
  const current = begin()
  expect(current()).toBe(true)
  wrapper.unmount()
  expect(current()).toBe(false)
})
