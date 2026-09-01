import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import { apiPost, clearToken, getToken, setToken } from "@/lib/api"

interface AuthContextValue {
  token: string | null
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setTokenState] = useState<string | null>(() => getToken())

  const login = useCallback(async (username: string, password: string) => {
    // Passe par le client partagé pour bénéficier de la normalisation des
    // erreurs (`ApiError`) : sans elle, un 400 remonte « Request failed with
    // status code 400 » au lieu du message du serveur.
    const { token: newToken } = await apiPost<{ token: string }>(
      "/token-auth/",
      { username, password },
    )
    setToken(newToken)
    setTokenState(newToken)
  }, [])

  const logout = useCallback(() => {
    clearToken()
    setTokenState(null)
  }, [])

  const value = useMemo(
    () => ({
      token,
      isAuthenticated: Boolean(token),
      login,
      logout,
    }),
    [token, login, logout],
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