import { useCallback, useEffect, useEffectEvent, useState } from "react"
import i18next from "i18next"
import { isCancelled } from "@/lib/api"
import type { Paginated } from "@/lib/types"

/** Durée pendant laquelle une liste de référentiel est considérée à jour. */
export const REFERENTIEL_TTL_MS = 5 * 60 * 1000

interface Entry {
  promise: Promise<unknown>
  value?: unknown
  fetchedAt?: number
}

const cache = new Map<string, Entry>()
const listeners = new Set<() => void>()

/**
 * Vide le cache — tout, une seule clé, ou celles qu'un prédicat retient
 * (`(clé) => clé.startsWith("country:")`) — après une écriture qui rend la
 * liste obsolète : création d'un pays, d'une équipe, import d'un classeur…
 */
export function invalidateReferentiel(key?: string | ((key: string) => boolean)) {
  if (key === undefined) cache.clear()
  else if (typeof key === "function") {
    for (const existing of [...cache.keys()]) {
      if (key(existing)) cache.delete(existing)
    }
  } else cache.delete(key)
  listeners.forEach((listener) => listener())
}

function readFresh(key: string, now: number): Entry | undefined {
  const entry = cache.get(key)
  if (!entry) return undefined
  if (entry.fetchedAt !== undefined && now - entry.fetchedAt > REFERENTIEL_TTL_MS) {
    cache.delete(key)
    return undefined
  }
  return entry
}

function load<T>(key: string, fetcher: () => Promise<T>): Promise<T> {
  const fresh = readFresh(key, Date.now())
  if (fresh) return fresh.promise as Promise<T>
  const entry: Entry = {
    promise: fetcher().then(
      (value) => {
        entry.value = value
        entry.fetchedAt = Date.now()
        return value
      },
      (error: unknown) => {
        // Un échec ne doit pas être servi depuis le cache pendant cinq minutes.
        if (cache.get(key) === entry) cache.delete(key)
        throw error
      },
    ),
  }
  cache.set(key, entry)
  return entry.promise as Promise<T>
}

export interface ReferentielResult<T> {
  data: T | null
  loading: boolean
  error: string | null
  reload: () => void
}

/**
 * Liste de référentiel (pays, équipes, projets, managers…) partagée entre les
 * pages et gardée en mémoire cinq minutes.
 *
 * Chaque page rechargeait ces listes à chaque changement de filtre alors
 * qu'elles ne bougent qu'au gré du back-office. Le cache est par clé, donc
 * par URL : deux pages qui demandent la même liste partagent la même requête.
 */
export function useReferentiel<T>(
  key: string,
  fetcher: () => Promise<T>,
  options: { enabled?: boolean } = {},
): ReferentielResult<T> {
  const { enabled = true } = options
  const run = useEffectEvent(() => load(key, fetcher))
  const [version, setVersion] = useState(0)
  const [state, setState] = useState<{ key: string | null; data: T | null; error: string | null }>(
    () => {
      const entry = enabled ? readFresh(key, Date.now()) : undefined
      return entry?.value !== undefined
        ? { key, data: entry.value as T, error: null }
        : { key: null, data: null, error: null }
    },
  )

  useEffect(() => {
    if (!enabled) return
    let active = true
    run()
      .then((data) => {
        if (active) setState({ key, data, error: null })
      })
      .catch((e: unknown) => {
        if (!active || isCancelled(e)) return
        setState((current) => ({
          key,
          data: current.data,
          error: e instanceof Error ? e.message : i18next.t("erreurs.referentiel_indisponible"),
        }))
      })
    return () => {
      active = false
    }
  }, [key, enabled, version])

  // Une invalidation ailleurs dans l'application relance la lecture.
  useEffect(() => {
    const listener = () => setVersion((v) => v + 1)
    listeners.add(listener)
    return () => {
      listeners.delete(listener)
    }
  }, [])

  const reload = useCallback(() => {
    cache.delete(key)
    setVersion((v) => v + 1)
  }, [key])

  return {
    data: state.data,
    loading: enabled && state.key !== key,
    error: state.error,
    reload,
  }
}

/** Vrai si la page reçue ne contient pas tout ce que le serveur connaît. */
export function isTruncated(page: Paginated<unknown> | null | undefined): boolean {
  return Boolean(page && page.count > page.results.length)
}

/** Taille demandée pour une liste de référentiel : au-delà, l'écran signale la troncature. */
export const REFERENTIEL_PAGE_SIZE = 200
