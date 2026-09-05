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
export type Budget = Schema<"Budget">
export type BudgetSummary = Schema<"BudgetSummary">
export type ReallocationStatus = Schema<"ReallocationStatusEnum">
export type Reallocation = Schema<"BudgetReallocation">
export type ExchangeRate = Schema<"ExchangeRate">

// ---------------------------------------------------------------------------
// Dossiers, dépenses et justificatifs
// ---------------------------------------------------------------------------

export type WorkflowStatus = Schema<"WorkflowStatusEnum">

/**
 * Actions de saisie qu'un dossier ou une ligne se voient proposer
 * (`allowed_actions`) : modifier, ajouter une ligne, déposer une pièce,
 * supprimer. Le serveur les calcule — brouillon ou non, auteur ou non,
 * droit ou non — et l'interface n'a aucune liste d'états à recopier.
 */
type EditAction = "edit" | "add_line" | "upload" | "delete"

/** Transitions d'un dossier ; ses lignes partent avec lui à la soumission. */
export type TransitionName = Exclude<Schema<"TransitionEnum">, "reopen" | EditAction>

/** Une ligne ne se soumet jamais seule : c'est le dossier qu'on soumet. */
export type ExpenseTransitionName = Exclude<TransitionName, "submit">

export type Dossier = Schema<"Dossier">
export type DossierDetail = Schema<"DossierDetail">
export type Expense = Schema<"Expense">
export type PaymentMethod = Schema<"PaymentMethodEnum">
export type ProofStatus = Schema<"ProofStatusEnum">
export type Proof = Schema<"Proof">
export type RegisterEntry = Schema<"ExpenseRegister">
export type Beneficiary = Schema<"Beneficiary">


// ---------------------------------------------------------------------------
// Pilotage, alertes et notifications
// ---------------------------------------------------------------------------

export type AlertLevel = Schema<"NotificationLevelEnum">
export type Dashboard = Schema<"Dashboard">
export type BreakdownRow = Schema<"BreakdownRow">
export type Breakdown = Schema<"Breakdown">
export type AppNotification = Schema<"Notification">
export type AuditEntry = Schema<"AuditLog">

// ---------------------------------------------------------------------------
// Back-office
// ---------------------------------------------------------------------------

export type Configuration = Schema<"Configuration">
export type WorkflowConfiguration = Schema<"WorkflowConfiguration">
export type PermissionMatrix = Schema<"PermissionMatrix">
