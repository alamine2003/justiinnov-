import { useEffect, useState } from "react"

/**
 * Valeur retardée : ne change qu'une fois la saisie stabilisée.
 *
 * Un champ de recherche déclenchait une requête à chaque frappe ; le serveur
 * en recevait dix pour un mot, et l'interface affichait la dernière arrivée,
 * pas la dernière tapée.
 */
export function useDebouncedValue<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs)
    return () => window.clearTimeout(timer)
  }, [value, delayMs])

  return debounced
}
