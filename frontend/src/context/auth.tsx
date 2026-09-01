import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import { apiPost, clearToken, getToken, setToken } from "@/lib/api"
import { fetchMe } from "@/lib/accounts"
import type { Me, Permissions } from "@/lib/types"

interface AuthContextValue {
  token: string | null
  isAuthenticated: boolean
  /** Profil courant : rôle, périmètre et droits. `null` tant qu'il charge. */
  me: Me | null
  loadingProfile: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
  refreshProfile: () => Promise<void>
  /** Le backend reste seul juge : ceci ne sert qu'à masquer l'inutile. */
  can: (permission: keyof Permissions) => boolean
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(() => getToken())
  const [me, setMe] = useState<Me | null>(null)
  const [loadingProfile, setLoadingProfile] = useState(false)

  const logout = useCallback(() => {
    clearToken()
    setTokenState(null)
    setMe(null)
  }, [])

  const refreshProfile = useCallback(async () => {
    if (!getToken()) {
      setMe(null)
      return
    }
    setLoadingProfile(true)
    try {
      setMe(await fetchMe())
    } catch {
      // Jeton périmé ou révoqué : on repart d'une session propre.
      logout()
    } finally {
      setLoadingProfile(false)
    }
  }, [logout])

  const login = useCallback(
    async (username: string, password: string) => {
      // Passe par le client partagé pour bénéficier de la normalisation des
      // erreurs (`ApiError`) : sans elle, un 400 remonte « Request failed with
      // status code 400 » au lieu du message du serveur.
      const { token: newToken } = await apiPost<{ token: string }>(
        "/token-auth/",
        { username, password },
      )
      setToken(newToken)
      setTokenState(newToken)
      await refreshProfile()
    },
    [refreshProfile],
  )

  useEffect(() => {
    if (token && !me) {
      void refreshProfile()
    }
    // `me` est volontairement absent des dépendances : le profil ne doit être
    // rechargé que lorsque le jeton change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, refreshProfile])

  const can = useCallback(
    (permission: keyof Permissions) => Boolean(me?.permissions?.[permission]),
    [me],
  )

  const value = useMemo(
    () => ({
      token,
      isAuthenticated: Boolean(token),
      me,
      loadingProfile,
      login,
      logout,
      refreshProfile,
      can,
    }),
    [token, me, loadingProfile, login, logout, refreshProfile, can],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error("useAuth doit être utilisé dans un AuthProvider")
  }
  return ctx
}
