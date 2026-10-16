/** 从生成契约推导方法、路径、参数和响应；保留既有 Axios 认证/刷新/错误链路。 */
import request from './request'
import type { operations } from './generated/schema'
import { sdkRoutes } from './generated/routes'

type Content<T> = T extends { content: infer C } ? C : never
type RequestContent<O> = O extends { requestBody?: infer B } ? Content<NonNullable<B>> : never
type MediaBody<C> = { [K in keyof C]: { body: C[K] } & (K extends 'application/json' ? { contentType?: K } : { contentType: K }) }[keyof C]
type BodyOptions<O> = [RequestContent<O>] extends [never] ? { body?: never; contentType?: never }
  : O extends { requestBody: unknown } ? MediaBody<RequestContent<O>> : Partial<MediaBody<RequestContent<O>>>
type Parameters<O> = O extends { parameters: infer P } ? P : never
type ParameterOption<P, K extends 'path' | 'query'> = P extends Record<K, infer V> ? { [Key in K]: V }
  : P extends { [Key in K]?: infer V } ? { [Key in K]?: V } : { [Key in K]?: never }
type SuccessResponse<O> = O extends { responses: infer R } ? { [K in keyof R]: `${K & (string | number)}` extends `2${string}` ? R[K] : never }[keyof R] : never
type SuccessContent<O> = Content<SuccessResponse<O>>
export type SDKResult<O> = [SuccessContent<O>] extends [never] ? undefined
  : 'application/json' extends keyof SuccessContent<O> ? SuccessContent<O>['application/json'] : Blob
type ResponseOptions<O> = 'application/json' extends keyof SuccessContent<O> ? { responseType?: 'json' }
  : [SuccessContent<O>] extends [never] ? { responseType?: 'json' } : { responseType: 'blob' }
type Options<O> = O extends unknown ? ParameterOption<Parameters<O>, 'path'> & ParameterOption<Parameters<O>, 'query'> & BodyOptions<O> & ResponseOptions<O> & {
  signal?: AbortSignal
  headers?: Readonly<Record<string, string>>
} : never
type Arguments<O> = {} extends Options<O> ? [options?: Options<O>] : [options: Options<O>]

interface RuntimeOptions {
  path?: Record<string, string | number>
  query?: Record<string, unknown>
  body?: unknown
  contentType?: string
  responseType?: 'json' | 'blob'
  signal?: AbortSignal
  headers?: Readonly<Record<string, string>>
}

function encodeBody(body: unknown, contentType: string | undefined): unknown {
  if (contentType !== 'multipart/form-data' && contentType !== 'application/x-www-form-urlencoded') return body
  if (!body || typeof body !== 'object' || body instanceof Blob) throw new Error('Form body must be an object')
  const form = contentType === 'multipart/form-data' ? new FormData() : new URLSearchParams()
  for (const [key, value] of Object.entries(body)) {
    for (const item of Array.isArray(value) ? value : [value]) {
      if (item === undefined) continue
      if (item instanceof Blob) {
        if (!(form instanceof FormData)) throw new Error('Binary uploads require multipart/form-data')
        form.append(key, item)
      } else form.append(key, item === null ? '' : typeof item === 'object' ? JSON.stringify(item) : String(item))
    }
  }
  return form
}

export function sdk<K extends keyof operations>(
  operation: K, ...args: Arguments<NoInfer<operations[K]>>
): Promise<SDKResult<operations[K]>>
export async function sdk(operation: string, options: RuntimeOptions = {}): Promise<unknown> {
  if (!Object.prototype.hasOwnProperty.call(sdkRoutes, operation)) throw new Error('Unknown SDK operation')
  const [method, template] = sdkRoutes[operation as keyof typeof sdkRoutes]
  if (!template.startsWith('/api/v1/') || /[?#\\]/.test(template)) throw new Error('SDK requires an API v1 path')
  const used = new Set<string>()
  const url = template.slice('/api/v1'.length).replace(/\{([^}]+)\}/g, (_match, key: string) => {
    const value = options.path?.[key]
    if ((typeof value !== 'string' && typeof value !== 'number') || !String(value)
      || ['.', '..'].includes(String(value)) || /[/\\\u0000-\u001f]/.test(String(value))) throw new Error('Invalid SDK path parameter')
    used.add(key)
    return encodeURIComponent(String(value))
  })
  if (Object.keys(options.path || {}).some(key => !used.has(key))) throw new Error('Unexpected SDK path parameter')
  const headers = { ...options.headers }
  // 浏览器/HTTP 适配器为 FormData 生成 boundary；不手写 multipart Content-Type。
  if (options.contentType === 'multipart/form-data') {
    for (const key of Object.keys(headers)) if (key.toLowerCase() === 'content-type') delete headers[key]
  }
  if (options.contentType && options.contentType !== 'multipart/form-data') headers['Content-Type'] = options.contentType
  const response = await request.request<unknown>({
    method, url, params: options.query, data: encodeBody(options.body, options.contentType),
    headers, signal: options.signal, responseType: options.responseType || 'json', paramsSerializer: { indexes: null },
  })
  return response.status === 204 || response.status === 205 ? undefined : response.data
}
