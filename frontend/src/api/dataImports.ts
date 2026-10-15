import request, { type ApiResponse } from './request'

export type ImportResource = 'roles' | 'posts'

export async function importResource(resource: ImportResource, file: File, signal?: AbortSignal) {
  const form = new FormData()
  form.append('resource', resource)
  form.append('file', file)
  const response = await request.post<ApiResponse<{ id: string }>>('/data-io/import/', form, { signal })
  return response.data.data
}

export async function importTemplate(resource: ImportResource, signal?: AbortSignal) {
  const response = await request.get<Blob>('/data-io/template/', { params: { resource }, responseType: 'blob', signal })
  return response.data
}
