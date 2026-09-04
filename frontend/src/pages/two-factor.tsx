import { TotpNotice } from "@/components/layout/totp-notice"

/**
 * Écran d'enrôlement de la double authentification : seul écran accessible
 * quand le serveur l'impose, écran ordinaire quand le titulaire vient
 * l'activer de lui-même. Voir `TotpNotice` pour le pourquoi.
 */
export function TwoFactorPage() {
  return <TotpNotice />
}
