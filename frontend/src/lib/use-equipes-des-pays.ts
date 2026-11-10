import { useEffect, useRef, useState } from "react"
import { fetchCountry } from "@/lib/countries"
import type { Team } from "@/lib/types"

/**
 * Les équipes actives de chaque pays coché, lues sur sa fiche à mesure des
 * coches. `actif` faux : rien n'est demandé (un compte du siège n'a pas
 * d'équipe à choisir).
 *
 * Chaque fiche n'est demandée qu'une fois. Les pays déjà demandés vivent
 * hors de l'état : sans cela, la table figurait dans les dépendances de
 * l'effet, chaque réponse le relançait, et son nettoyage jetait les requêtes
 * encore en vol — k pays cochés produisaient k + (k−1) + … requêtes pour k
 * fiches. Une fiche illisible donne une liste vide, et le pays sort des
 * demandes pour qu'un nouveau cochage puisse retenter.
 */
export function useEquipesDesPays(countryIds: number[], actif: boolean): Record<number, Team[]> {
  const [teamsByCountry, setTeamsByCountry] = useState<Record<number, Team[]>>({})
  const demandes = useRef(new Set<number>())

  useEffect(() => {
    if (!actif) return
    const missing = countryIds.filter((id) => !demandes.current.has(id))
    if (missing.length === 0) return
    let active = true
    for (const id of missing) {
      demandes.current.add(id)
      fetchCountry(id)
        .then((country) => {
          if (!active) return
          setTeamsByCountry((current) => ({
            ...current,
            [id]: country.teams.filter((team) => team.is_active),
          }))
        })
        .catch(() => {
          // Sans la fiche, aucune équipe à proposer pour ce pays : le
          // serveur revalidera de toute façon.
          demandes.current.delete(id)
          if (active) setTeamsByCountry((current) => ({ ...current, [id]: [] }))
        })
    }
    return () => {
      active = false
    }
  }, [actif, countryIds])

  return teamsByCountry
}
