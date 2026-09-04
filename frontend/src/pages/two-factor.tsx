import { TotpNotice } from "@/components/layout/totp-notice"

/**
 * Seul écran accessible tant que la double authentification n'est pas
 * enrôlée. Voir `TotpNotice` pour le pourquoi.
 */
export function TwoFactorPage() {
  return <TotpNotice />
}
