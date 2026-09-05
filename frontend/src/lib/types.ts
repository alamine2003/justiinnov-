/**
 * Types du contrat d'API.
 *
 * Les formes des réponses viennent du schéma OpenAPI du backend
 * (`docs/api/schema.json` → `types.generated.ts`, régénérés par
 * `npm run types:api`). Ce fichier n'en garde que des alias, sous les noms
 * que l'interface emploie, et les quelques types composés ou utilitaires que
 * le schéma ne peut pas dire (générique de pagination, constantes du
 * circuit). Un champ nouveau se déclare dans le sérialiseur, jamais ici.
 */
import type { components } from "@/lib/types.generated"

type Schemas = components["schemas"]

/** Composant du schéma, par son nom OpenAPI. */
export type Schema<K extends keyof Schemas> = Schemas[K]

// ---------------------------------------------------------------------------
// Référentiel
// ---------------------------------------------------------------------------

export type Manager = Schema<"Manager">
export type Team = Schema<"Team">
export type CostCenter = Schema<"CostCenter">
export type ProjectStatus = Schema<"ProjectStatusEnum">
export type Project = Schema<"Project">
export type ExpenseTitle = Schema<"ExpenseTitle">
export type MarketingCategory = Schema<"MarketingCategory">
export type CountrySummary = Schema<"CountryList">
export type CountryDetail = Schema<"CountryDetail">
export type ChangeLogEntry = Schema<"ChangeLog">
/** Pays africain proposé à la création, non encore suivi. */
export type AvailableCountry = Schema<"AvailableCountry">

/**
 * Réponse d'une liste. Le schéma en décrit une par ressource
 * (`PaginatedExpenseList`…) ; l'interface n'a besoin que de la forme.
 */
export interface Paginated<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

// ---------------------------------------------------------------------------
// Comptes, rôles et périmètres
// ---------------------------------------------------------------------------

/** Les libellés des rôles, comme ceux des statuts, vivent dans `lib/labels.ts`. */
export type Role = Schema<"RoleEnum">
export type ScopeCountry = Schema<"ScopeCountry">
export type ScopeTeam = Schema<"ScopeTeam">
/**
 * Droits calculés par le serveur à partir du rôle. L'interface ne redéfinit
 * jamais la matrice : elle s'en sert seulement pour masquer l'inutile.
 */
export type Permissions = Schema<"Permissions">
export type Me = Schema<"Me">
export type AccountUser = Schema<"User">
/** Secret d'enrôlement, remis une seule fois par `POST /me/2fa/enrol/`. */
export type TotpEnrolment = Schema<"TotpEnrolment">

// ---------------------------------------------------------------------------
// Budgets
// ---------------------------------------------------------------------------

export type OverrunPolicy = Schema<"OverrunPolicyEnum">
/** Indicateurs calculés côté serveur — jamais recalculés dans l'interface. */
export type BudgetFigures = Schema<"BudgetFigures">
/** Dimension découpée par une sous-enveloppe (`Budget.scope_kind`). */
export type BudgetScope = "country" | "project" | "team" | "manager"
export type Budget = Schema<"Budget">
export type CountryBudgetRow = Schema<"CountryBudgetRow">
export type BudgetSummary = Schema<"BudgetSummary">
export type ReallocationStatus = Schema<"ReallocationStatusEnum">
export type Reallocation = Schema<"BudgetReallocation">
export type ExchangeRate = Schema<"ExchangeRate">

// ---------------------------------------------------------------------------
// Dossiers, dépenses et justificatifs
// ---------------------------------------------------------------------------

export type WorkflowStatus = Schema<"WorkflowStatusEnum">

/**
 * Une dépense déclarée est irréversible : elle ne se modifie plus.
 * Doit refléter `expenses.workflow.LOCKED_STATUSES`.
 */
export const LOCKED_STATUSES: WorkflowStatus[] = [
  "submitted",
  "in_review",
  "justified",
  "unjustified",
  "closed",
]

/** Seul un brouillon peut encore être retiré, par son auteur. */
export const DELETABLE_STATUSES: WorkflowStatus[] = ["draft"]

/**
 * Une pièce se dépose jusqu'à la clôture : une dépense non justifiée peut
 * encore l'être par une preuve arrivée après coup.
 */
export const PROOF_LOCKED_STATUSES: WorkflowStatus[] = ["closed"]

/** Transitions d'un dossier ; ses lignes partent avec lui à la soumission. */
export type TransitionName = Exclude<Schema<"TransitionEnum">, "reopen">

/** Une ligne ne se soumet jamais seule : c'est le dossier qu'on soumet. */
export type ExpenseTransitionName = Exclude<TransitionName, "submit">

export type DossierTotals = Schema<"DossierTotals">
export type Dossier = Schema<"Dossier">
export type DossierDetail = Schema<"DossierDetail">
export type Expense = Schema<"Expense">
export type PaymentMethod = Schema<"PaymentMethodEnum">
export type ProofStatus = Schema<"ProofStatusEnum">
export type Proof = Schema<"Proof">
/** Pièce vue depuis une dépense, dans le registre de justification. */
export type ExpenseProof = Schema<"ExpenseProof">
export type RegisterEntry = Schema<"ExpenseRegister">
export type Beneficiary = Schema<"Beneficiary">

/** Réponse d'une transition : l'objet, et l'avertissement s'il y a lieu. */
export type DossierTransitionResponse = Schema<"DossierTransitionResponse">
export type ExpenseTransitionResponse = Schema<"ExpenseTransitionResponse">

// ---------------------------------------------------------------------------
// Pilotage, alertes et notifications
// ---------------------------------------------------------------------------

export type AlertLevel = Schema<"NotificationLevelEnum">
export type Alert = Schema<"Alert">
export type DashboardTotals = Schema<"DashboardTotals">
export type DashboardCountryRow = Schema<"DashboardCountryRow">
export type Dashboard = Schema<"Dashboard">
export type BreakdownRow = Schema<"BreakdownRow">
export type Breakdown = Schema<"Breakdown">
export type AppNotification = Schema<"Notification">
export type AuditEntry = Schema<"AuditLog">
export type ImportResult = Schema<"ImportResult">

// ---------------------------------------------------------------------------
// Back-office
// ---------------------------------------------------------------------------

export type Configuration = Schema<"Configuration">
export type WorkflowConfiguration = Schema<"WorkflowConfiguration">
export type Capability = Schema<"PermissionMatrixCapability">
export type PermissionMatrix = Schema<"PermissionMatrix">
