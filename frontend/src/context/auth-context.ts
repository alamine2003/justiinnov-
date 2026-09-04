import { createContext } from "react"
import type { Me, Permissions } from "@/lib/types"

export interface AuthContextValue {
  token: string | null
  isAuthenticated: boolean
  /** Profil courant : rôle, périmètre et droits. `null` tant qu'il charge. */
  me: Me | null
  loadingProfile: boolean
  /** Échec de lecture du profil qui n'est pas une perte de session (panne, 502). */
  profileError: string | null
  /** `code` : code de double authentification, exigé une fois l'enrôlement confirmé. */
  login: (username: string, password: string, code?: string) => Promise<void>
  logout: () => Promise<void>
  refreshProfile: () => Promise<void>
  /** Remplace le jeton de session, après un changement de mot de passe. */
  replaceToken: (token: string) => void
  /** Le backend reste seul juge : ceci ne sert qu'à masquer l'inutile. */
  can: (permission: keyof Permissions) => boolean
}

export const AuthContext = createContext<AuthContextValue | null>(null)
