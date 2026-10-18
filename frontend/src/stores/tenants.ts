import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import request from '@/api/request'

export interface TenantOption { id: string; slug: string; name: string; role: string }

function storedTenantId() {
  try { return localStorage.getItem('admincore.tenant') || '' } catch { return '' }
}

export const useTenantStore = defineStore('tenants', () => {
  const options = ref<TenantOption[]>([])
  const currentId = ref(storedTenantId())
  const loaded = ref(false)
  const current = computed(() => options.value.find(item => item.id === currentId.value))
  let generation = 0

  async function load() {
    if (loaded.value) return
    const owner = generation
    const response = await request.get<{ data: TenantOption[] }>('/organization/my-tenants/')
    if (owner !== generation) return
    options.value = Array.isArray(response.data.data) ? response.data.data : []
    if (currentId.value && !options.value.some(item => item.id === currentId.value)) currentId.value = ''
    if (!currentId.value && options.value.length) currentId.value = options.value[0].id
    if (currentId.value) localStorage.setItem('admincore.tenant', currentId.value)
    else localStorage.removeItem('admincore.tenant')
    loaded.value = true
  }

  function select(id: string) {
    if (!options.value.some(item => item.id === id)) return
    currentId.value = id
    localStorage.setItem('admincore.tenant', id)
  }

  function clear() {
    generation++
    options.value = []
    currentId.value = ''
    loaded.value = false
    localStorage.removeItem('admincore.tenant')
  }

  return { options, currentId, current, loaded, load, select, clear }
})
