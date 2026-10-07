import type { Paginated, ProjectType } from "@/lib/types"

/** Les trois types d'origine, tels que la migration `core.0018` les crée (décision 119). */
export const TYPES_DE_PROJETS: ProjectType[] = [
  ["congres", "Congrès", "Congress"],
  ["voyage", "Voyage", "Trip"],
  ["soutien_financier", "Soutien financier", "Financial support"],
].map(([code, name, name_en], index) => ({
  id: index + 1, code, name, name_en, libelle: name, description: "", ordre: index + 1,
  is_active: true, dossier_kinds_actifs: 1, projets: 0, created_at: "", updated_at: "",
}))

/** La réponse de `GET /api/project-types/`, pour les simulations de `@/lib/countries`. */
export function pageDesTypesDeProjets(): Promise<Paginated<ProjectType>> {
  return Promise.resolve({
    count: TYPES_DE_PROJETS.length, next: null, previous: null, results: TYPES_DE_PROJETS,
  })
}
