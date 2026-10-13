import { defineStore } from 'pinia'
import { ref } from 'vue'
import request, { type ApiResponse } from '@/api/request'

interface ModuleDescriptor {
  key: string
  title: string
  enabled: boolean
  dependencies: string[]
  paths: string[]
}
interface Capabilities {
  contract_version: number
  preset: string
  modules: ModuleDescriptor[]
}

export const useModuleStore = defineStore('modules', () => {
  const config = ref<Capabilities | null>(null)
  let pending: Promise<void> | undefined
  let fetchedAt = 0
  async function load(force = false) {
    if (!force && config.value && Date.now() - fetchedAt < 30000) return
    if (!pending) pending = request.get<ApiResponse<Capabilities>>('/modules/').then(response => {
      const value = response.data.data
      if (!value || value.contract_version !== 1 || !Array.isArray(value.modules) ||
          value.modules.some(module => !module || typeof module.key !== 'string' || typeof module.enabled !== 'boolean' ||
            !Array.isArray(module.paths) || module.paths.some(path => typeof path !== 'string' || !path.startsWith('/')) ||
            !Array.isArray(module.dependencies) || module.dependencies.some(key => typeof key !== 'string')) ||
          new Set(value.modules.map(module => module.key)).size !== value.modules.length) throw new Error('不支持的模块契约')
      config.value = value
      fetchedAt = Date.now()
    }).catch(error => { config.value = null; throw error }).finally(() => { pending = undefined })
    return pending
  }
  function enabled(key: string) {
    return config.value?.modules.some(module => module.key === key && module.enabled) ?? false
  }
  function pathEnabled(path: string) {
    return !!config.value && config.value.modules.every(module =>
      !module.paths.some(base => path === base || path.startsWith(base + '/')) || module.enabled)
  }
  return { config, load, enabled, pathEnabled }
})
