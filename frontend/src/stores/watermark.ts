import { defineStore } from 'pinia'
import { ref } from 'vue'

const STORAGE_KEY = 'admincore:page-watermark'

/** Only a browser preference is persisted; identity remains in the auth store. */
export const useWatermarkStore = defineStore('watermark', () => {
  const enabled = ref(false)
  const persistenceAvailable = ref(true)
  try {
    enabled.value = localStorage.getItem(STORAGE_KEY) === 'true'
  } catch {
    persistenceAvailable.value = false
  }

  function setEnabled(value: boolean) {
    enabled.value = value
    try {
      localStorage.setItem(STORAGE_KEY, String(value))
      persistenceAvailable.value = true
    } catch {
      persistenceAvailable.value = false
    }
  }

  return { enabled, persistenceAvailable, setEnabled }
})
