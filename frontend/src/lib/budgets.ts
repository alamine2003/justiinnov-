import { apiGet, apiPatch, apiPost } from "@/lib/api"
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
export function fetchBudgets(params?: Record<string, unknown>) {
  return apiGet<Paginated<Budget>>("/budgets/", params)
}

export function fetchBudgetSummary(params?: Record<string, unknown>) {
  return apiGet<BudgetSummary>("/budgets/summary/", params)
}

export function createBudget(data: unknown) {
  return apiPost<Budget>("/budgets/", data)
}

export function updateBudget(id: number, data: unknown) {
  return apiPatch<Budget>(`/budgets/${id}/`, data)
}

// ---------------------------------------------------------------------------
// Réallocations
// ---------------------------------------------------------------------------
export function fetchReallocations(params?: Record<string, unknown>) {
  return apiGet<Paginated<Reallocation>>("/reallocations/", params)
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
export function fetchExchangeRates(params?: Record<string, unknown>) {
  return apiGet<Paginated<ExchangeRate>>("/exchange-rates/", params)
}

export function createExchangeRate(data: unknown) {
  return apiPost<ExchangeRate>("/exchange-rates/", data)
}
