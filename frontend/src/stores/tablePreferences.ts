import { defineStore } from 'pinia'
import { ref } from 'vue'

export type TableDensity = 'comfortable' | 'compact'
export const TABLE_DENSITY_KEY = 'admincore.table-density'

/** 本浏览器的显示偏好，不包含账号信息，不写入服务端。 */
export const useTablePreferencesStore = defineStore('table-preferences', () => {
  const density = ref<TableDensity>('comfortable')
  const persistenceUnavailable = ref(false)
  try {
    if (localStorage.getItem(TABLE_DENSITY_KEY) === 'compact') density.value = 'compact'
  } catch { persistenceUnavailable.value = true }

  function setDensity(value: TableDensity) {
    if (value !== 'comfortable' && value !== 'compact') return
    density.value = value
    try {
      localStorage.setItem(TABLE_DENSITY_KEY, value)
      persistenceUnavailable.value = false
    } catch { persistenceUnavailable.value = true }
  }

  return { density, persistenceUnavailable, setDensity }
})
