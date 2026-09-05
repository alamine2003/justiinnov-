import { apiGet, apiPatch, apiPost } from "@/lib/api"
import type {
  AvailableCountry,
  ChangeLogEntry,
  CostCenter,
  CountryDetail,
  CountrySummary,
  ExpenseTitle,
  Manager,
  MarketingCategory,
  Paginated,
  Project,
  Team,
} from "@/lib/types"

// ---------------------------------------------------------------------------
// Pays
// ---------------------------------------------------------------------------
export function fetchCountries(params?: Record<string, unknown>, signal?: AbortSignal) {
  return apiGet<Paginated<CountrySummary>>("/countries/", params, signal)
}

export function fetchCountry(id: number, signal?: AbortSignal) {
  return apiGet<CountryDetail>(`/countries/${id}/`, undefined, signal)
}

export function createCountry(data: unknown) {
  return apiPost<CountrySummary>("/countries/", data)
}

export function updateCountry(id: number, data: unknown) {
  return apiPatch<CountrySummary>(`/countries/${id}/`, data)
}

export function updateCountryManagers(id: number, managerIds: number[]) {
  return apiPatch<CountrySummary>(`/countries/${id}/`, { managers: managerIds })
}

// ---------------------------------------------------------------------------
// Managers
// ---------------------------------------------------------------------------
export function createManager(data: unknown) {
  return apiPost<Manager>("/managers/", data)
}

export function updateManager(id: number, data: unknown) {
  return apiPatch<Manager>(`/managers/${id}/`, data)
}

// ---------------------------------------------------------------------------
// Équipes
// ---------------------------------------------------------------------------
export function fetchTeams(params?: Record<string, unknown>) {
  return apiGet<Paginated<Team>>("/teams/", params)
}

export function createTeam(data: unknown) {
  return apiPost<Team>("/teams/", data)
}

export function updateTeam(id: number, data: unknown) {
  return apiPatch<Team>(`/teams/${id}/`, data)
}

// ---------------------------------------------------------------------------
// Centres de coûts
// ---------------------------------------------------------------------------
export function createCostCenter(data: unknown) {
  return apiPost<CostCenter>("/cost-centers/", data)
}

export function updateCostCenter(id: number, data: unknown) {
  return apiPatch<CostCenter>(`/cost-centers/${id}/`, data)
}

// ---------------------------------------------------------------------------
// Projets
// ---------------------------------------------------------------------------
export function fetchProjects(params?: Record<string, unknown>) {
  return apiGet<Paginated<Project>>("/projects/", params)
}

export function createProject(data: unknown) {
  return apiPost<Project>("/projects/", data)
}

export function updateProject(id: number, data: unknown) {
  return apiPatch<Project>(`/projects/${id}/`, data)
}

// ---------------------------------------------------------------------------
// Intitulés de dépenses
// ---------------------------------------------------------------------------
export function createExpenseTitle(data: unknown) {
  return apiPost<ExpenseTitle>("/expense-titles/", data)
}

export function updateExpenseTitle(id: number, data: unknown) {
  return apiPatch<ExpenseTitle>(`/expense-titles/${id}/`, data)
}

// ---------------------------------------------------------------------------
// Catégories marketing
// ---------------------------------------------------------------------------
export function createMarketingCategory(data: unknown) {
  return apiPost<MarketingCategory>("/marketing-categories/", data)
}

export function updateMarketingCategory(id: number, data: unknown) {
  return apiPatch<MarketingCategory>(`/marketing-categories/${id}/`, data)
}

// ---------------------------------------------------------------------------
// Historique
// ---------------------------------------------------------------------------
export function fetchHistory(params?: Record<string, unknown>, signal?: AbortSignal) {
  return apiGet<Paginated<ChangeLogEntry>>("/history/", params, signal)
}

/**
 * Pays africains que la plateforme ne suit pas encore.
 *
 * La liste vient du serveur, là où la validation s'applique : la recopier ici
 * la ferait diverger au premier ajout.
 */
export function fetchAvailableCountries() {
  return apiGet<AvailableCountry[]>("/countries/disponibles/")
}
