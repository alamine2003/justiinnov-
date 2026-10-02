import { useSearchParams } from "react-router-dom"

/**
 * Les filtres de l'audit vivent dans l'URL (`?debut=&fin=&country=`, puis
 * ceux de chaque onglet) : une tuile de la vue d'ensemble ouvre le journal
 * déjà filtré, et l'adresse se partage telle quelle. Passer d'un onglet à
 * l'autre garde la période et le pays.
 */
export function useFiltresAudit() {
  const [params, setParams] = useSearchParams()
  const lire = (cle: string) => params.get(cle) ?? ""
  const changer = (valeurs: Record<string, string>) =>
    setParams(
      (actuels) => {
        const suivants = new URLSearchParams(actuels)
        for (const [cle, valeur] of Object.entries(valeurs)) {
          if (valeur) suivants.set(cle, valeur)
          else suivants.delete(cle)
        }
        return suivants
      },
      { replace: true },
    )
  return { lire, changer }
}

/** Les paramètres d'API communs : période et pays, quand ils sont posés. */
export function bornes(lire: (cle: string) => string): Record<string, string> {
  const resultat: Record<string, string> = {}
  for (const cle of ["debut", "fin", "country"]) {
    if (lire(cle)) resultat[cle] = lire(cle)
  }
  return resultat
}
