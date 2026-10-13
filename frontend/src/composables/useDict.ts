import { ref, onMounted } from 'vue'
import { systemApi, type DictionaryItem } from '@/api/system'
import { uiText } from '@/i18n/uiText'

export function useDict(code: string) {
  const items = ref<DictionaryItem[]>([])
  const loading = ref(false)
  const error = ref('')
  const version = ref(0)
  async function reload() {
    loading.value = true
    error.value = ''
    try {
      const data = await systemApi.options(code)
      items.value = data.items
      version.value = data.version
    } catch {
      items.value = []
      version.value = 0
      error.value = uiText('字典加载失败，请重试')
    } finally {
      loading.value = false
    }
  }
  onMounted(reload)
  return { items, loading, error, version, reload }
}
