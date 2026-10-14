import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import request, { type ApiResponse } from '@/api/request'
import { frontendExtensions } from '@/modules/registry'

interface ModuleDescriptor {
  key: string
  title: string
  enabled: boolean
  dependencies: string[]
  paths: string[]
  page_permissions?: Record<string, string>
}
interface Capabilities {
  contract_version: number
  preset: string
  modules: ModuleDescriptor[]
  scope_resources?: Array<{ key: string; title: string }>
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
            (module.page_permissions !== undefined && (!module.page_permissions || typeof module.page_permissions !== 'object' || Array.isArray(module.page_permissions) ||
              Object.entries(module.page_permissions).some(([path, code]) => !module.paths.includes(path) || typeof code !== 'string' || !/^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$/.test(code)))) ||
            !Array.isArray(module.dependencies) || module.dependencies.some(key => typeof key !== 'string')) ||
          new Set(value.modules.map(module => module.key)).size !== value.modules.length) throw new Error('不支持的模块契约')
      if (value.scope_resources !== undefined && (!Array.isArray(value.scope_resources) || value.scope_resources.some(row => !row || typeof row.key !== 'string' || typeof row.title !== 'string') || new Set(value.scope_resources.map(row => row.key)).size !== value.scope_resources.length)) throw new Error('不支持的数据范围契约')
      config.value = value
      fetchedAt = Date.now()
    }).catch(error => { config.value = null; throw error }).finally(() => { pending = undefined })
    return pending
  }
  function enabled(key: string) {
    return config.value?.modules.some(module => module.key === key && module.enabled) ?? false
  }
  function pathEnabled(path: string) {
    if (frontendExtensions.some(extension => (path === extension.path || path.startsWith(extension.path + '/')) && !enabled(extension.key))) return false
    return !!config.value && config.value.modules.every(module =>
      !module.paths.some(base => path === base || path.startsWith(base + '/')) || module.enabled)
  }
  const pagePermissions = computed<Record<string, string>>(() => Object.assign({}, ...(config.value?.modules.map(module => module.page_permissions || {}) ?? [])))
  return { config, load, enabled, pathEnabled, pagePermissions }
})
