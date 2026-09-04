import { useCallback, useSyncExternalStore } from "react"

/**
 * Installation de l'application (PWA) depuis l'interface.
 *
 * Chrome et Edge émettent `beforeinstallprompt` quand la page est
 * installable ; l'événement doit être retenu pour être rejoué au clic sur
 * « Installer l'application ». Il part souvent avant le montage de React :
 * `captureInstallPrompt` s'abonne dès le chargement du module principal.
 */
interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>
}

let deferred: BeforeInstallPromptEvent | null = null
const listeners = new Set<() => void>()

function notify() {
  listeners.forEach((listener) => listener())
}

export function captureInstallPrompt() {
  window.addEventListener("beforeinstallprompt", (event) => {
    // Sans `preventDefault`, Chrome affiche sa propre bannière au moment de
    // son choix ; ici, l'invitation attend le clic de l'utilisateur.
    event.preventDefault()
    deferred = event as BeforeInstallPromptEvent
    notify()
  })
  window.addEventListener("appinstalled", () => {
    deferred = null
    notify()
  })
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

function isAvailable() {
  return deferred !== null
}

/** `available` n'est vrai que sur un navigateur qui sait installer la page. */
export function useInstallPrompt() {
  const available = useSyncExternalStore(subscribe, isAvailable, () => false)

  const install = useCallback(async () => {
    const event = deferred
    if (!event) return
    await event.prompt()
    const { outcome } = await event.userChoice
    if (outcome === "accepted") {
      deferred = null
      notify()
    }
  }, [])

  return { available, install }
}
