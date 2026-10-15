/** 每次发送读取当前偏好，刷新、公开认证和SSE共享相同语言白名单。 */
export function apiLanguage(): 'en' | 'zh-Hans' {
  return localStorage.getItem('language') === 'en-US' ? 'en' : 'zh-Hans'
}
