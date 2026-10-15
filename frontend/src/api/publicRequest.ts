import axios from 'axios'
import { apiLanguage } from './language'

/** 公开恢复和验证码共用无JWT、无认证刷新拦截器的独立传输。 */
const publicRequest = axios.create({ baseURL: (import.meta.env.VITE_API_BASE_URL as string) || '/api/v1', timeout: 30000 })
publicRequest.interceptors.request.use(config => {
  config.headers['Accept-Language'] = apiLanguage()
  return config
})
export default publicRequest
