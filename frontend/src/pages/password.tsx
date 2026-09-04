import { PasswordNotice } from "@/components/layout/password-notice"

/**
 * Seul écran accessible tant que le mot de passe provisoire n'est pas
 * remplacé. Voir `PasswordNotice` pour le pourquoi.
 */
export function PasswordPage() {
  return <PasswordNotice />
}
