import { api, apiGet, apiPatch, apiPost } from "@/lib/api"
import type {
  Budget,
  BudgetSummary,
  ExchangeRate,
  Paginated,
  Reallocation,
} from "@/lib/types"

// ---------------------------------------------------------------------------
// Enveloppes
// ---------------------------------------------------------------------------
export function fetchBudgets(params?: Record<string, unknown>, signal?: AbortSignal) {
  return apiGet<Paginated<Budget>>("/budgets/", params, signal)
}

export function fetchBudgetSummary(params?: Record<string, unknown>, signal?: AbortSignal) {
  return apiGet<BudgetSummary>("/budgets/summary/", params, signal)
}

export function createBudget(data: unknown) {
  return apiPost<Budget>("/budgets/", data)
}

export function updateBudget(id: number, data: unknown) {
  return apiPatch<Budget>(`/budgets/${id}/`, data)
}

/**
 * Supprime une enveloppe qui n'a jamais servi (décision 91).
 *
 * Le serveur refuse celle qui porte une dépense, une réallocation ou des
 * sous-enveloppes : elle se désactive. `can_delete` dit d'avance ce qu'il
 * accepterait.
 */
export function deleteBudget(id: number) {
  return api.delete(`/budgets/${id}/`)
}

// ---------------------------------------------------------------------------
// Réallocations
// ---------------------------------------------------------------------------
export function fetchReallocations(params?: Record<string, unknown>, signal?: AbortSignal) {
  return apiGet<Paginated<Reallocation>>("/reallocations/", params, signal)
}

export function createReallocation(data: unknown) {
  return apiPost<Reallocation>("/reallocations/", data)
}

export function approveReallocation(id: number, note?: string) {
  return apiPost<Reallocation>(`/reallocations/${id}/approve/`, { note: note ?? "" })
}

export function rejectReallocation(id: number, note: string) {
  return apiPost<Reallocation>(`/reallocations/${id}/reject/`, { note })
}

// ---------------------------------------------------------------------------
// Taux de change
// ---------------------------------------------------------------------------
export function fetchExchangeRates(params?: Record<string, unknown>, signal?: AbortSignal) {
  return apiGet<Paginated<ExchangeRate>>("/exchange-rates/", params, signal)
}

export function createExchangeRate(data: unknown) {
  return apiPost<ExchangeRate>("/exchange-rates/", data)
}
