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
  country_ref: string | null
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

// ---------------------------------------------------------------------------
// Comptes, rôles et périmètres
// ---------------------------------------------------------------------------

export type Role =
  | "super_admin"
  | "admin"
  | "doo"
  | "country_manager"
  | "owner"
  | "controller"
  | "auditor"

export const ROLE_LABELS: Record<Role, string> = {
  super_admin: "Super administrateur",
  admin: "Administrateur plateforme",
  doo: "Direction des opérations",
  country_manager: "Responsable pays",
  owner: "Manager / Owner",
  controller: "Contrôleur / Finance",
  auditor: "Auditeur",
}

export interface ScopeCountry {
  id: number
  name: string
  code: string
  country_ref: string | null
}

/**
 * Droits calculés par le serveur à partir du rôle. L'interface ne redéfinit
 * jamais la matrice : elle s'en sert seulement pour masquer l'inutile.
 */
export interface Permissions {
  manage_users: boolean
  manage_countries: boolean
  manage_subentities: boolean
  manage_budgets: boolean
  record_expenses: boolean
  validate_expenses: boolean
  view_audit: boolean
}

export interface Me {
  id: number
  username: string
  first_name: string
  last_name: string
  email: string
  role: Role
  role_display: string
  countries: ScopeCountry[]
  has_global_scope: boolean
  must_change_password: boolean
  permissions: Permissions
}

export interface AccountUser {
  id: number
  username: string
  first_name: string
  last_name: string
  email: string
  is_active: boolean
  /** `null` pour un compte technique hérité, sans profil. */
  role: Role | null
  countries: number[]
  countries_detail: ScopeCountry[]
  must_change_password: boolean
}

// ---------------------------------------------------------------------------
// Budgets
// ---------------------------------------------------------------------------

export type OverrunPolicy = "block" | "warn" | "approval"

export const OVERRUN_POLICY_LABELS: Record<OverrunPolicy, string> = {
  block: "Bloquer",
  warn: "Alerter",
  approval: "Soumettre à approbation",
}

/** Indicateurs calculés côté serveur — jamais recalculés dans l'interface. */
export interface BudgetFigures {
  consumed: string
  justified: string
  gap: string
  remaining: string
  execution_rate: string | null
  justification_rate: string | null
  amount_xof: string | null
  remaining_xof: string | null
}

export interface Budget {
  id: number
  country: number
  country_name: string
  country_ref: string | null
  currency: string
  year: number
  project: number | null
  project_name: string | null
  amount: string
  overrun_policy: OverrunPolicy
  overrun_policy_display: string
  is_active: boolean
  figures: BudgetFigures
  created_at: string
  updated_at: string
}

export interface CountryBudgetRow {
  country: number
  country_name: string
  country_ref: string | null
  currency: string
  allocated: string
  sub_allocated: string
  consumed: string
  justified: string
  remaining: string
  remaining_xof: string | null
}

export interface BudgetSummary {
  countries: CountryBudgetRow[]
  total_remaining_xof: string
  unconverted_currencies: string[]
}

export type ReallocationStatus = "pending" | "approved" | "rejected"

export interface Reallocation {
  id: number
  source: number
  source_label: string
  target: number
  target_label: string
  amount: string
  reason: string
  status: ReallocationStatus
  status_display: string
  requested_by: string
  decided_by: string
  decided_at: string | null
  decision_note: string
  created_at: string
  updated_at: string
}

export interface ExchangeRate {
  id: number
  currency: string
  rate_to_xof: string
  valid_from: string
  created_at: string
}

// ---------------------------------------------------------------------------
// Dossiers, dépenses et justificatifs
// ---------------------------------------------------------------------------

export type WorkflowStatus =
  | "draft"
  | "submitted"
  | "in_review"
  | "approved"
  | "rejected"
  | "closed"

export const WORKFLOW_LABELS: Record<WorkflowStatus, string> = {
  draft: "Brouillon",
  submitted: "Soumis",
  in_review: "En contrôle",
  approved: "Validé",
  rejected: "Refusé",
  closed: "Clôturé",
}

/** Doit refléter `expenses.workflow.LOCKED_STATUSES`. */
export const LOCKED_STATUSES: WorkflowStatus[] = ["approved", "closed"]

export type TransitionName = "submit" | "review" | "approve" | "reject" | "close"

export interface DossierTotals {
  amount: string
  justified: string
  gap: string
}

export interface Dossier {
  id: number
  number: string
  label: string
  country: number
  country_name: string
  country_ref: string | null
  currency: string
  team: number | null
  team_name: string | null
  owner: number | null
  owner_name: string | null
  date: string
  status: WorkflowStatus
  status_display: string
  note: string
  totals: DossierTotals
  expense_count: number
  proof_count: number
  created_at: string
  updated_at: string
}

export interface Expense {
  id: number
  dossier: number
  dossier_number: string
  country: number
  country_name: string
  currency: string
  team: number | null
  team_name: string | null
  owner: number | null
  owner_name: string | null
  date: string
  place: string
  title: string
  description: string
  project: number | null
  project_name: string | null
  expense_title: number | null
  marketing_category: number | null
  beneficiary: number | null
  beneficiary_name: string | null
  budget: number | null
  budget_label: string | null
  amount: string
  justified_amount: string
  gap: string
  payment_method: string
  payment_method_display: string
  status: WorkflowStatus
  status_display: string
  note: string
  created_by: string
  created_at: string
  updated_at: string
}

export type ProofStatus =
  | "received"
  | "incomplete"
  | "to_review"
  | "validated"
  | "rejected"
  | "archived"

export const PROOF_STATUS_LABELS: Record<ProofStatus, string> = {
  received: "Reçu",
  incomplete: "Incomplet",
  to_review: "À contrôler",
  validated: "Validé",
  rejected: "Rejeté",
  archived: "Archivé",
}

export const PROOF_KIND_LABELS: Record<string, string> = {
  receipt: "Reçu",
  invoice: "Facture",
  discharge: "Décharge",
  deliverable: "Livrable",
  other: "Autre",
}

export interface Proof {
  id: number
  dossier: number
  original_name: string
  kind: string
  kind_display: string
  status: ProofStatus
  status_display: string
  is_complete: boolean
  sha256: string
  size: number
  content_type: string
  version: number
  replaces: number | null
  uploaded_by: string
  rejection_reason: string
  download_url: string
  created_at: string
  updated_at: string
}

export interface DossierDetail extends Dossier {
  expenses: Expense[]
  proofs: Proof[]
}

export interface Beneficiary {
  id: number
  name: string
  kind: string
  kind_display: string
  contact: string
  is_active: boolean
}

export interface AuditEntry {
  id: number
  user: string
  action: string
  action_display: string
  object_type: string
  object_id: number
  label: string
  country: number | null
  country_name: string | null
  detail: Record<string, unknown>
  ip_address: string | null
  user_agent: string
  created_at: string
}