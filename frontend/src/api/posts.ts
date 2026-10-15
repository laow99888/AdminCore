import request, { type ApiResponse, type PagedData } from './request'
export interface PostRow { id: string; code: string; name: string; description: string; order: number; is_active: boolean; version: number }
export interface UserPostRow { id: string; user: string; username: string; post: string; post_name: string; post_active: boolean; user_active: boolean; version: number }
export type PostSection = 'posts' | 'user-posts'
export const postsApi = {
  list: async <T>(section: PostSection, params: { page: number; page_size: number; search: string }) => (await request.get<ApiResponse<PagedData<T>>>(`/organization/${section}/`, { params })).data.data,
  detail: async (id: string, signal?: AbortSignal) => (await request.get<ApiResponse<PostRow>>(`/organization/posts/${id}/`, { signal })).data.data,
  save: (id: string, data: Omit<PostRow, 'id'>) => id ? request.patch(`/organization/posts/${id}/`, data) : request.post('/organization/posts/', data),
  assign: (user: string, post: string) => request.post('/organization/user-posts/', { user, post, version: 0 }),
  remove: (section: PostSection, id: string, version: number) => request.delete(`/organization/${section}/${id}/`, { params: { version } }),
  choices: async () => (await request.get<ApiResponse<PostRow[]>>('/organization/posts/choices/')).data.data,
}
