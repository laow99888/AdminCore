import { defineStore } from 'pinia'
import { ref } from 'vue'
import request, { type ApiResponse } from '@/api/request'

export const useBrandStore = defineStore('brand', () => {
  const name = ref('AdminCore')
  const tagline = ref('现代化中后台管理系统')
  const logo = ref('')
  async function load() {
    try {
      const { data } = await request.get<ApiResponse<{ name: string; tagline: string; logo?: string }>>('/brand/')
      if (typeof data.data.name === 'string' && typeof data.data.tagline === 'string') {
        name.value = data.data.name
        tagline.value = data.data.tagline
        logo.value = data.data.logo?.startsWith('data:image/png;base64,') ? data.data.logo : ''
        document.title = name.value
      }
    } catch { /* 品牌失败使用默认值，不能阻断登录。 */ }
  }
  return { name, tagline, logo, load }
})
