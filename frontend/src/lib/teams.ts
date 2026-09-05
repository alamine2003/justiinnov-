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

/**
 * Vrai pour un manager rattaché à des équipes : le serveur refuse un dossier
 * ou une ligne sans équipe (« Choisissez une de vos équipes. »), le
 * formulaire l'exige donc avant d'envoyer.
 */
export function teamRequired(me: Me | null): boolean {
  return Boolean(me?.teams && me.teams.length > 0)
}
