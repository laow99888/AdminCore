import request, { type ApiResponse } from './request'

export interface FileReferenceStatus { protected: boolean; lifecycle_version: number }

export async function fileReferenceStatus(id: string, signal?: AbortSignal): Promise<FileReferenceStatus> {
  return (await request.get<ApiResponse<FileReferenceStatus>>(`/files/${id}/references/`, { signal })).data.data
}
