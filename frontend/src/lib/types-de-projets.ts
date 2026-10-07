import { fetchProjectTypes } from "@/lib/countries"
import { REFERENTIEL_PAGE_SIZE, useReferentiel } from "@/lib/referentiel"
import type { ProjectType } from "@/lib/types"

/** Clé du cache partagé : la configuration l'invalide après chaque écriture. */
export const CLE_DES_TYPES_DE_PROJETS = "project-types:tous"

/**
 * La liste commune des types de projets, dans l'ordre de la configuration
 * (décision 119), actifs et désactivés.
 *
 * Elle remplace la liste figée dans l'interface jusqu'à la 2.1 : un type
 * que le super administrateur ajoute paraît dans les filtres et le
 * formulaire de projet sans nouvelle version. Les formulaires ne proposent
 * que les types actifs (`typesActifs`) ; les filtres gardent les désactivés,
 * dont les projets existent toujours.
 */
export function useTypesDeProjets() {
  return useReferentiel(CLE_DES_TYPES_DE_PROJETS, () =>
    fetchProjectTypes({ page_size: REFERENTIEL_PAGE_SIZE }).then((page) => page.results),
  )
}

export function typesActifs(types: ProjectType[] | null | undefined): ProjectType[] {
  return (types ?? []).filter((type) => type.is_active)
}
