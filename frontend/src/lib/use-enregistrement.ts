import { useState } from "react"

/**
 * Le message d'un refus : celui de l'erreur quand elle en porte un (le
 * serveur l'a rédigé dans la langue de l'interface), sinon celui donné.
 */
export function messageDErreur(err: unknown, parDefaut: string): string {
  return err instanceof Error ? err.message : parDefaut
}

/**
 * Ce qu'un refus affiche : un message par défaut, ou une fonction qui lit
 * l'erreur — elle peut ranger les erreurs de champ ailleurs et ne rien
 * renvoyer pour l'en-tête du formulaire (`null`).
 */
export type LectureDuRefus = string | ((err: unknown) => string | null)

/**
 * Le motif « enregistrer » d'un formulaire : l'indicateur d'envoi, l'erreur,
 * et l'envoi lui-même entre les deux.
 *
 * Il était recopié vingt-neuf fois (écart 20 de la revue d'architecture) :
 * `setSaving(true)`, `setError(null)`, un `try`, le message de l'erreur ou un
 * message par défaut, `setSaving(false)` dans le `finally`. `enregistrer`
 * fait exactement cela autour de `ecrire`, qui contient tout ce que le `try`
 * contenait — l'appel, la relecture, la fermeture du dialogue —, et dit si
 * l'envoi a abouti. La validation reste avant l'appel, dans le formulaire.
 */
export function useEnregistrement(refus: LectureDuRefus) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const enregistrer = async (ecrire: () => Promise<unknown>): Promise<boolean> => {
    setSaving(true)
    setError(null)
    try {
      await ecrire()
      return true
    } catch (err) {
      setError(typeof refus === "string" ? messageDErreur(err, refus) : refus(err))
      return false
    } finally {
      setSaving(false)
    }
  }

  return { saving, error, setError, enregistrer }
}
