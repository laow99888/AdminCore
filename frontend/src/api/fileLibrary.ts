import request, { type ApiResponse } from './request'

export interface FileOrganization { version: number; folder: string | null; tags: string[] }
export interface FileFolder { id: string; name: string; parent: string | null; version: number }
export interface FileLibrary { folders: FileFolder[]; tags: string[]; tags_truncated: boolean }
export interface FileLibraryFilter { folder: string; tag: string; search: string }
function normalizeLibrary(value: unknown): FileLibrary {
  if (!value || typeof value !== 'object') return { folders: [], tags: [], tags_truncated: false }
  const data = value as Partial<FileLibrary>
  return {
    folders: Array.isArray(data.folders) ? data.folders : [],
    tags: Array.isArray(data.tags) ? data.tags : [],
    tags_truncated: data.tags_truncated === true,
  }
}
export const fileLibraryApi = {
  load: async (signal?: AbortSignal) => normalizeLibrary((await request.get<ApiResponse<FileLibrary>>('/files/library/', { signal })).data.data),
  createFolder: async (name: string, parent: string | null) =>
    (await request.post<ApiResponse<FileFolder>>('/files/library/folders/', { name, parent })).data.data,
  saveFolder: async (row: FileFolder, name: string, parent: string | null) =>
    (await request.put<ApiResponse<FileFolder>>(`/files/library/folders/${row.id}/`, { version: row.version, name, parent })).data.data,
  deleteFolder: (row: FileFolder) => request.delete(`/files/library/folders/${row.id}/`, { data: { version: row.version } }),
  organize: async (id: string, values: FileOrganization) =>
    (await request.put<ApiResponse<FileOrganization>>(`/files/${id}/organization/`, values)).data.data,
}
