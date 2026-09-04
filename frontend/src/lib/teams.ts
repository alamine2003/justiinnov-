import type { Me } from "@/lib/types"

/**
 * Restreint une liste d'équipes au périmètre du profil.
 *
 * Un manager rattaché à des équipes ne saisit que pour elles : le serveur
 * refuserait une autre équipe, et la liste complète du pays ne ferait que
 * mener à ce refus. Les autres rôles, sans équipe de périmètre, voient tout.
 */
export function scopedTeams<T extends { id: number }>(teams: T[], me: Me | null): T[] {
  const ids = me?.teams?.map((team) => team.id) ?? []
  if (ids.length === 0) return teams
  return teams.filter((team) => ids.includes(team.id))
}
