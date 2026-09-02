import { api, apiGet, apiPatch, apiPost } from "@/lib/api"
import type {
  AuditEntry,
  Beneficiary,
  Dossier,
  DossierDetail,
  Expense,
  Paginated,
  Proof,
  ProofStatus,
  TransitionName,
} from "@/lib/types"

// ---------------------------------------------------------------------------
// Dossiers (N°ORDRE)
// ---------------------------------------------------------------------------
export function fetchDossiers(params?: Record<string, unknown>) {
  return apiGet<Paginated<Dossier>>("/dossiers/", params)
}

export function fetchDossier(id: number) {
  return apiGet<DossierDetail>(`/dossiers/${id}/`)
}

export function createDossier(data: unknown) {
  return apiPost<Dossier>("/dossiers/", data)
}

export function updateDossier(id: number, data: unknown) {
  return apiPatch<Dossier>(`/dossiers/${id}/`, data)
}

export function transitionDossier(
  id: number,
  action: TransitionName,
  note?: string,
) {
  return apiPost<Dossier & { warning?: string }>(`/dossiers/${id}/${action}/`, {
    note: note ?? "",
  })
}

// ---------------------------------------------------------------------------
// Dépenses
// ---------------------------------------------------------------------------
export function fetchExpenses(params?: Record<string, unknown>) {
  return apiGet<Paginated<Expense>>("/expenses/", params)
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
  action: TransitionName,
  note?: string,
) {
  return apiPost<Expense & { warning?: string }>(`/expenses/${id}/${action}/`, {
    note: note ?? "",
  })
}

// ---------------------------------------------------------------------------
// Justificatifs
// ---------------------------------------------------------------------------
export function uploadProof(form: FormData) {
  // Axios détecte le FormData et pose lui-même la frontière multipart.
  return apiPost<Proof>("/proofs/", form)
}

export function reviewProof(id: number, status: ProofStatus, reason?: string) {
  return apiPost<Proof>(`/proofs/${id}/review/`, { status, reason: reason ?? "" })
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
  URL.revokeObjectURL(url)
}

// ---------------------------------------------------------------------------
// Bénéficiaires et audit
// ---------------------------------------------------------------------------
export function fetchBeneficiaries(params?: Record<string, unknown>) {
  return apiGet<Paginated<Beneficiary>>("/beneficiaries/", params)
}

export function createBeneficiary(data: unknown) {
  return apiPost<Beneficiary>("/beneficiaries/", data)
}

export function fetchAudit(params?: Record<string, unknown>) {
  return apiGet<Paginated<AuditEntry>>("/audit/", params)
}
