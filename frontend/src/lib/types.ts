export interface Manager {
  id: number
  name: string
  email: string
  title: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface Team {
  id: number
  country: number
  country_name: string
  name: string
  description: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface CostCenter {
  id: number
  country: number
  country_name: string
  code: string
  name: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export type ProjectStatus = "planned" | "active" | "on_hold" | "completed"

export interface Project {
  id: number
  country: number
  country_name: string
  name: string
  description: string
  status: ProjectStatus
  budget: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface ExpenseTitle {
  id: number
  country: number
  country_name: string
  label: string
  description: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface MarketingCategory {
  id: number
  country: number
  country_name: string
  name: string
  description: string
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface CountrySummary {
  id: number
  name: string
  code: string
  currency: string
  currency_symbol: string
  timezone: string
  is_active: boolean
  managers: Manager[]
  team_count: number
  cost_center_count: number
  project_count: number
  created_at: string
  updated_at: string
}

export interface CountryDetail extends CountrySummary {
  teams: Team[]
  cost_centers: CostCenter[]
  projects: Project[]
  expense_titles: ExpenseTitle[]
  marketing_categories: MarketingCategory[]
  expense_title_count: number
  marketing_category_count: number
}

export interface ChangeLogEntry {
  id: number
  model_name: string
  model_name_display: string
  object_id: number
  label: string
  action: string
  action_display: string
  country: number | null
  country_name: string | null
  from_value: string
  to_value: string
  changed_fields: string[]
  performed_by: string
  created_at: string
}

export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}