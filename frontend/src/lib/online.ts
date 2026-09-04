import { useSyncExternalStore } from "react"

function subscribe(listener: () => void) {
  window.addEventListener("online", listener)
  window.addEventListener("offline", listener)
  return () => {
    window.removeEventListener("online", listener)
    window.removeEventListener("offline", listener)
  }
}

function isOnline() {
  return typeof navigator === "undefined" || navigator.onLine !== false
}

/** Vrai tant que le navigateur se croit connecté au réseau. */
export function useOnline(): boolean {
  return useSyncExternalStore(subscribe, isOnline, () => true)
}
