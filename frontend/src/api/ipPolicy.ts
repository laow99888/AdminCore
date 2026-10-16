import request, { type ApiResponse } from './request'

export interface IPPolicyConfig { enabled: boolean; allow: string[]; deny: string[] }
export interface IPPolicy extends IPPolicyConfig { version: number; updated_at: string }
export interface IPPolicyPreview { source_ip: string | null; allowed: boolean }
export const ipPolicyApi = {
  async detail(_id = '1', signal?: AbortSignal) {
    return (await request.get<ApiResponse<IPPolicy>>('/ip-policy/', { signal })).data.data
  },
  async preview(data: IPPolicyConfig, signal?: AbortSignal) {
    return (await request.post<ApiResponse<IPPolicyPreview>>('/ip-policy/preview/', data, { signal })).data.data
  },
  async save(data: IPPolicyConfig & { version: number; current_password: string }) {
    return (await request.put<ApiResponse<IPPolicy>>('/ip-policy/', data)).data.data
  },
}
