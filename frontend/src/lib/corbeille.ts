import { api, apiGet, apiPost } from "@/lib/api"
import type { ElementSupprime, NatureSupprimee, Paginated, ResultatCorbeille } from "@/lib/types"

/**
 * La corbeille du super administrateur (décision 120). Elle ne se vide ni
 * ne se modifie : l'API n'a pas de `PUT`, de `PATCH` ni de `DELETE`.
 */
export function fetchCorbeille(params?: Record<string, unknown>, signal?: AbortSignal) {
  return apiGet<Paginated<ElementSupprime>>("/corbeille/", params, signal)
}

/** Met un objet à la corbeille, avec ce qui en dépend ; le motif est obligatoire. */
export function mettreALaCorbeille(nature: NatureSupprimee, id: number, motif: string) {
  return apiPost<ResultatCorbeille>("/corbeille/", { nature, id, motif })
}

/**
 * Télécharge le justificatif gardé par la corbeille. Comme une pièce, il
 * exige le jeton : il passe par le client HTTP, pas par un lien direct.
 */
export async function telechargerDepuisLaCorbeille(element: ElementSupprime) {
  const response = await api.get(`/corbeille/${element.id}/fichier/`, { responseType: "blob" })
  const url = URL.createObjectURL(response.data as Blob)
  const link = document.createElement("a")
  link.href = url
  const nom = (element.donnees as { original_name?: string } | null)?.original_name
  link.download = nom || `justificatif-${element.objet_id}`
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
}
