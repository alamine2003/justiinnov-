/**
 * Les dix-sept filiales du groupe, telles que la page d'accueil les nomme.
 *
 * La liste de référence est `backend/core/africa.py` (`AFRICAN_COUNTRIES`) :
 * c'est elle qui interdit de créer un pays hors périmètre. La page d'accueil
 * s'affiche avant toute session, donc sans l'API ; elle recopie les codes,
 * et le test `perimetre.test.ts` relit le fichier Python pour refuser toute
 * divergence. Les noms sont traduits par le dictionnaire (`filiales.<code>`).
 */
export const FILIALES = [
  "BF", "BJ", "CD", "CG", "CI", "CM", "DJ", "GA", "GM",
  "GN", "MG", "ML", "MR", "NE", "SN", "TD", "TG",
] as const

export type CodeFiliale = (typeof FILIALES)[number]
