import { useCallback, useEffect, useEffectEvent, useState } from "react"
import { useTranslation } from "react-i18next"
import { isCancelled } from "@/lib/api"

interface QueryState<T> {
  stamp: string | null
  /** Clé sans le numéro de rechargement : ce que les données décrivent. */
  cle: string | null
  data: T | null
  error: string | null
}

export interface QueryResult<T> {
  data: T | null
  /** Vrai tant que la réponse correspondant aux paramètres courants n'est pas arrivée. */
  loading: boolean
  /** Rafraîchissement d'un résultat déjà affiché, à distinguer du premier chargement. */
  refreshing: boolean
  error: string | null
  reload: () => void
  /** Remplace le résultat sans repasser par le serveur (mise à jour ciblée). */
  setData: (updater: T | ((current: T | null) => T | null)) => void
}

/**
 * Charge une ressource dès que sa clé change, en annulant la requête
 * précédente.
 *
 * Deux filtres tapés vite produisaient deux requêtes ; si la première
 * répondait en dernier, elle écrasait la bonne. Ici, changer la clé aborte la
 * requête en cours, et une réponse d'une requête abandonnée est ignorée.
 *
 * L'état n'est modifié qu'à l'arrivée de la réponse : `loading` se déduit de
 * la clé, ce qui évite un rendu supplémentaire à chaque changement de filtre.
 *
 * La langue fait partie de la clé : les libellés que le serveur rend
 * (`*_display`, alertes) suivent `Accept-Language`, et un changement de
 * langue recharge donc ce qui est affiché.
 */
export function useQuery<T>(
  key: string,
  fetcher: (signal: AbortSignal) => Promise<T>,
  options: { enabled?: boolean; fallback?: string } = {},
): QueryResult<T> {
  const { t, i18n } = useTranslation()
  const { enabled = true, fallback = t("erreurs.chargement_impossible") } = options
  const [version, setVersion] = useState(0)
  const [state, setState] = useState<QueryState<T>>({
    stamp: null,
    cle: null,
    data: null,
    error: null,
  })
  // Le fetcher est presque toujours une fermeture recréée à chaque rendu :
  // `useEffectEvent` en lit la dernière version sans relancer l'effet.
  const run = useEffectEvent((signal: AbortSignal) => fetcher(signal))

  const cle = enabled ? `${key}#${i18n.resolvedLanguage ?? i18n.language}` : null
  const stamp = cle === null ? null : `${cle}#${version}`

  useEffect(() => {
    if (stamp === null) return
    const controller = new AbortController()
    run(controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return
        setState({ stamp, cle, data, error: null })
      })
      .catch((e: unknown) => {
        if (controller.signal.aborted || isCancelled(e)) return
        setState((current) => ({
          stamp,
          cle,
          // Les données de la clé précédente ne décrivent plus ce qui est
          // demandé : les garder afficherait les brouillons sous le filtre
          // « justifié », sous un bandeau d'erreur — un résultat faux, présenté
          // comme un résultat. Un simple rechargement de la même clé, lui,
          // garde ce qui est à l'écran.
          data: current.cle === cle ? current.data : null,
          error: e instanceof Error ? e.message : fallback,
        }))
      })
    return () => controller.abort()
  }, [stamp, cle, fallback])

  const reload = useCallback(() => setVersion((v) => v + 1), [])
  const setData = useCallback(
    (updater: T | ((current: T | null) => T | null)) => {
      setState((current) => ({
        ...current,
        data:
          typeof updater === "function"
            ? (updater as (c: T | null) => T | null)(current.data)
            : updater,
      }))
    },
    [],
  )

  const loading = stamp !== null && state.stamp !== stamp
  return {
    data: state.data,
    loading,
    refreshing: loading && state.data !== null,
    error: state.error,
    reload,
    setData,
  }
}
