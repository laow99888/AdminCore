import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { useAuthStore } from './auth'
import { useTenantStore } from './tenants'
import request, { type ApiResponse } from '@/api/request'
import { frontendExtensions } from '@/modules/registry'

interface ModuleDescriptor {
  key: string
  title: string
  enabled: boolean
  dependencies: string[]
  paths: string[]
  page_permissions?: Record<string, string>
  data_io_resources?: string[]
}
interface Capabilities {
  contract_version: number
  preset: string
  modules: ModuleDescriptor[]
  scope_resources?: Array<{ key: string; title: string }>
  field_policy_resources?: Record<string, string[]>
}

export const useModuleStore = defineStore('modules', () => {
  const config = ref<Capabilities | null>(null)
  let pending: Promise<void> | undefined
  let fetchedAt = 0
  let generation = 0
  const auth = useAuthStore()
  const tenants = useTenantStore()
  function reset() { generation++; pending = undefined; fetchedAt = 0; config.value = null }
  watch([() => auth.user?.id, () => tenants.currentId], reset, { flush: 'sync' })
  async function load(force = false) {
    if (!force && config.value && Date.now() - fetchedAt < 30000) return
    const owner = generation
    if (!pending) pending = request.get<ApiResponse<Capabilities>>('/modules/').then(response => {
      if (owner !== generation) return
      const value = response.data.data
      if (!value || value.contract_version !== 1 || !Array.isArray(value.modules) ||
          value.modules.some(module => !module || typeof module.key !== 'string' || typeof module.enabled !== 'boolean' ||
            (module.data_io_resources !== undefined && (!Array.isArray(module.data_io_resources) || module.data_io_resources.some(resource => resource !== module.key))) ||
            !Array.isArray(module.paths) || module.paths.some(path => typeof path !== 'string' || !path.startsWith('/')) ||
            (module.page_permissions !== undefined && (!module.page_permissions || typeof module.page_permissions !== 'object' || Array.isArray(module.page_permissions) ||
              Object.entries(module.page_permissions).some(([path, code]) => !module.paths.includes(path) || typeof code !== 'string' || !/^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$/.test(code)))) ||
            !Array.isArray(module.dependencies) || module.dependencies.some(key => typeof key !== 'string')) ||
          new Set(value.modules.map(module => module.key)).size !== value.modules.length) throw new Error('不支持的模块契约')
      if (value.scope_resources !== undefined && (!Array.isArray(value.scope_resources) || value.scope_resources.some(row => !row || typeof row.key !== 'string' || typeof row.title !== 'string') || new Set(value.scope_resources.map(row => row.key)).size !== value.scope_resources.length)) throw new Error('不支持的数据范围契约')
      if (__ADMINCORE_MINIMAL_BUILD__ && value.modules.some(module => module.enabled)) throw new Error('精简前端无法加载已启用的可选模块，请同步重新构建完整前后端镜像')
      config.value = value
      fetchedAt = Date.now()
    }).catch(error => { if (owner === generation) config.value = null; throw error }).finally(() => { if (owner === generation) pending = undefined })
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
  return { config, load, enabled, pathEnabled, pagePermissions, reset }
})
