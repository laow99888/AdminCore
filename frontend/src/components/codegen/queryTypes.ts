import type { GeneratedField } from './types'

export interface QueryCondition { field: string; op: string; value: string | number | boolean }
export interface AdvancedQuery { match: 'all' | 'any'; conditions: QueryCondition[] }
export interface QueryDefinition { filters: Record<string, string>; advanced: AdvancedQuery; ordering: string }
export interface SavedQuery { id: string; name: string; shared: boolean; version: number; definition: QueryDefinition; editable: boolean; available?: boolean }
export interface SelectedRecord { id: string; version: number }
export interface BulkResult { id: string; status: string }
export const emptyAdvanced = (): AdvancedQuery => ({ match: 'all', conditions: [] })
export const queryOperators = (field?: GeneratedField) => ['eq', 'ne', ...(field?.query === 'contains' ? ['contains'] : []), ...(field?.query === 'range' ? ['gte', 'lte'] : [])]
