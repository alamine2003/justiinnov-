import { api, apiGet, apiPatch, apiPost } from "@/lib/api"
import type { AxiosProgressEvent } from "axios"
import type {
  AuditEntry,
  Beneficiary,
  Dossier,
  DossierDetail,
  Expense,
  ExpenseTransitionName,
  Paginated,
  Proof,
  ProofStatus,
  RegisterEntry,
  TransitionName,
} from "@/lib/types"

// ---------------------------------------------------------------------------
// Dossiers (N°ORDRE)
// ---------------------------------------------------------------------------
export function fetchDossiers(params?: Record<string, unknown>, signal?: AbortSignal) {
  return apiGet<Paginated<Dossier>>("/dossiers/", params, signal)
}

export function fetchDossier(id: number, signal?: AbortSignal) {
  return apiGet<DossierDetail>(`/dossiers/${id}/`, undefined, signal)
}

export function createDossier(data: unknown) {
  return apiPost<Dossier>("/dossiers/", data)
}

export function updateDossier(id: number, data: unknown) {
  return apiPatch<Dossier>(`/dossiers/${id}/`, data)
}

/** Charge utile d'une transition : motif, et montant justifié pour `justify`. */
export interface TransitionData {
  note?: string
  justified_amount?: string
}

/** Les transitions de dossier renvoient le détail complet, lignes et pièces comprises. */
export function transitionDossier(
  id: number,
  action: TransitionName,
  data: TransitionData = {},
) {
  return apiPost<DossierDetail & { warning?: string }>(`/dossiers/${id}/${action}/`, {
    note: data.note ?? "",
  })
}

/**
 * Ramène un dossier déclaré au brouillon, avec le motif qui sera conservé
 * dans le journal d'audit et transmis au pays.
 */
export function reopenDossier(id: number, note: string) {
  return apiPost<DossierDetail>(`/dossiers/${id}/reopen/`, { note })
}

// ---------------------------------------------------------------------------
// Dépenses
// ---------------------------------------------------------------------------
export function fetchExpenses(params?: Record<string, unknown>) {
  return apiGet<Paginated<Expense>>("/expenses/", params)
}

/**
 * Registre de justification : chaque dépense avec ses preuves.
 *
 * Le journal d'audit dit qui a fait quoi ; ce registre dit où est passé
 * l'argent et ce qui l'atteste.
 */
export function fetchRegister(params?: Record<string, unknown>, signal?: AbortSignal) {
  return apiGet<Paginated<RegisterEntry>>("/expenses/register/", params, signal)
}

export function createExpense(data: unknown) {
  return apiPost<Expense>("/expenses/", data)
}

export function updateExpense(id: number, data: unknown) {
  return apiPatch<Expense>(`/expenses/${id}/`, data)
}

/**
 * Supprime un brouillon.
 *
 * Une dépense déclarée est irréversible : le serveur refuse toute suppression
 * au-delà du brouillon.
 */
export function deleteExpenseDraft(id: number) {
  return api.delete(`/expenses/${id}/`)
}

export function transitionExpense(
  id: number,
  action: ExpenseTransitionName,
  data: TransitionData = {},
) {
  const payload: Record<string, string> = { note: data.note ?? "" }
  // Le montant justifié n'a de sens qu'à la justification ; le serveur le
  // prend égal à la dépense s'il est absent, et le remet à zéro au rejet.
  if (action === "justify" && data.justified_amount !== undefined) {
    payload.justified_amount = data.justified_amount
  }
  return apiPost<Expense & { warning?: string }>(`/expenses/${id}/${action}/`, payload)
}

// ---------------------------------------------------------------------------
// Justificatifs
// ---------------------------------------------------------------------------
export function uploadProof(
  form: FormData,
  onUploadProgress?: (event: AxiosProgressEvent) => void,
) {
  // Axios détecte le FormData et pose lui-même la frontière multipart.
  return apiPost<Proof>("/proofs/", form, { onUploadProgress })
}

export function reviewProof(id: number, status: ProofStatus, reason?: string) {
  return apiPost<Proof>(`/proofs/${id}/review/`, { status, reason: reason ?? "" })
}

/** Types affichables directement dans l'application. */
export function isPreviewable(proof: Proof): boolean {
  const name = proof.original_name.toLowerCase()
  return /\.(pdf|png|jpe?g|webp|gif)$/.test(name)
}

/**
 * Charge une pièce pour l'afficher.
 *
 * Le fichier n'ayant pas d'URL publique, il faut le récupérer avec le jeton
 * puis en faire une URL locale. L'appelant doit la révoquer après usage, sinon
 * le navigateur garde le contenu en mémoire.
 */
export async function loadProofBlob(proof: Proof) {
  const response = await api.get(`/proofs/${proof.id}/download/`, {
    responseType: "blob",
  })
  const blob = response.data as Blob
  return {
    url: URL.createObjectURL(blob),
    type: blob.type || "application/octet-stream",
  }
}

/**
 * Télécharge une pièce justificative.
 *
 * Le fichier n'est pas accessible par une URL publique : il faut présenter le
 * jeton, donc passer par le client HTTP plutôt que par un lien direct.
 */
export async function downloadProof(proof: Proof) {
  const response = await api.get(`/proofs/${proof.id}/download/`, {
    responseType: "blob",
  })
  const url = URL.createObjectURL(response.data as Blob)
  const link = document.createElement("a")
  link.href = url
  link.download = proof.original_name || `justificatif-${proof.id}`
  document.body.appendChild(link)
  link.click()
  link.remove()
  // Révoquée après coup : certains navigateurs n'ont pas encore lu le blob
  // au retour de `click()`, et le téléchargement tombait vide.
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

// ---------------------------------------------------------------------------
// Bénéficiaires et audit
// ---------------------------------------------------------------------------
export function fetchBeneficiaries(params?: Record<string, unknown>, signal?: AbortSignal) {
  return apiGet<Paginated<Beneficiary>>("/beneficiaries/", params, signal)
}

export function createBeneficiary(data: unknown) {
  return apiPost<Beneficiary>("/beneficiaries/", data)
}

export function updateBeneficiary(id: number, data: unknown) {
  return apiPatch<Beneficiary>(`/beneficiaries/${id}/`, data)
}

export function fetchAudit(params?: Record<string, unknown>, signal?: AbortSignal) {
  return apiGet<Paginated<AuditEntry>>("/audit/", params, signal)
}
