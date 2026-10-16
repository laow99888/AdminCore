import axios from 'axios'
import { apiLanguage } from './language'
import { API_BASE_URL } from './baseUrl'

/** 公开恢复和验证码共用无JWT、无认证刷新拦截器的独立传输。 */
const publicRequest = axios.create({ baseURL: API_BASE_URL, timeout: 30000 })
publicRequest.interceptors.request.use(config => {
  config.headers['Accept-Language'] = apiLanguage()
  return config
})
export default publicRequest
