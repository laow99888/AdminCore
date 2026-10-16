export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

/** SSE 不允许把 Bearer token 发送到跨源地址，也不接受凭据、查询或片段。 */
export function realtimeUrl(base = API_BASE_URL, origin = window.location.origin): string {
  const url = new URL(base, origin)
  if (url.origin !== origin || url.username || url.password || url.search || url.hash) throw new Error('Realtime requires a same-origin API base URL')
  return `${url.pathname.replace(/\/+$/, '')}/realtime/events/`
}
