import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react"
import { useNavigate } from "react-router-dom"
import i18next from "i18next"
import {
  ApiError,
  apiLogout,
  apiPost,
  clearToken,
  getToken,
  onPasswordChangeRequired,
  onTotpSetupRequired,
  onUnauthorized,
  setToken,
} from "@/lib/api"
import { TOTP_PATH, fetchMe } from "@/lib/accounts"
import { invalidateReferentiel } from "@/lib/referentiel"
import type { Me, Permissions } from "@/lib/types"
import { AuthContext } from "@/context/auth-context"
import { currentLanguage, isLanguage } from "@/i18n"

export function AuthProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate()
  const [token, setTokenState] = useState<string | null>(() => getToken())
  const [me, setMe] = useState<Me | null>(null)
  const [loadingProfile, setLoadingProfile] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)

  const clearSession = useCallback(() => {
    clearToken()
    setTokenState(null)
    setMe(null)
    setProfileError(null)
    // Les listes en mémoire appartiennent à la session : un autre compte,
    // avec un autre périmètre, ne doit pas en hériter.
    invalidateReferentiel()
  }, [])

  const logout = useCallback(async () => {
    try {
      if (getToken()) await apiLogout()
    } catch {
      // Le serveur peut être injoignable : la session locale se ferme quand même.
    } finally {
      clearSession()
    }
  }, [clearSession])

  const refreshProfile = useCallback(async () => {
    if (!getToken()) {
      setMe(null)
      return
    }
    setLoadingProfile(true)
    setProfileError(null)
    try {
      const profile = await fetchMe()
      setMe(profile)
      // La langue enregistrée sur le profil l'emporte : elle suit la
      // personne d'un poste à l'autre. Un serveur qui ne connaît pas encore
      // le champ laisse la langue du navigateur.
      if (isLanguage(profile.language) && profile.language !== currentLanguage()) {
        await i18next.changeLanguage(profile.language)
      }
    } catch (e) {
      // Seule une session refusée (jeton périmé ou révoqué) justifie de
      // repartir de zéro. Une panne réseau ou un 502 se signale, sans
      // déconnecter : l'utilisateur retrouverait sa session au retour du
      // serveur.
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) {
        clearSession()
      } else {
        const message = e instanceof Error ? e.message : i18next.t("erreurs.profil_indisponible")
        setProfileError(message)
        throw new Error(i18next.t("erreurs.profil_illisible", { message }))
      }
    } finally {
      setLoadingProfile(false)
    }
  }, [clearSession])

  const login = useCallback(
    async (username: string, password: string, code?: string) => {
      // Passe par le client partagé pour bénéficier de la normalisation des
      // erreurs (`ApiError`) : sans elle, un 400 remonte « Request failed with
      // status code 400 » au lieu du message du serveur. Le code n'est
      // envoyé que s'il a été saisi : le serveur dit lui-même s'il en faut un.
      const { token: newToken } = await apiPost<{ token: string }>(
        "/token-auth/",
        code ? { username, password, code } : { username, password },
      )
      setToken(newToken)
      setTokenState(newToken)
      await refreshProfile()
    },
    [refreshProfile],
  )

  const replaceToken = useCallback((newToken: string) => {
    setToken(newToken)
    setTokenState(newToken)
  }, [])

  useEffect(() => {
    if (token && !me) {
      refreshProfile().catch(() => {
        // L'erreur est déjà exposée par `profileError`.
      })
    }
    // `me` est volontairement absent des dépendances : le profil ne doit être
    // rechargé que lorsque le jeton change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, refreshProfile])

  // Le client HTTP signale une session perdue ; c'est ici qu'on en tire les
  // conséquences, parce que c'est ici que vivent l'état et le routeur.
  useEffect(() => {
    return onUnauthorized(() => {
      clearSession()
      navigate("/login", { replace: true })
    })
  }, [clearSession, navigate])

  useEffect(() => {
    const relire = () => {
      refreshProfile().catch(() => {
        // Déjà signalé par `profileError`.
      })
    }
    const unsubscribePassword = onPasswordChangeRequired(relire)
    // Le serveur a refusé une requête faute d'enrôlement : sa politique
    // fait foi, quoi que dise le profil en mémoire. On relit le profil et on
    // mène à l'écran d'enrôlement.
    const unsubscribeTotp = onTotpSetupRequired(() => {
      relire()
      navigate(TOTP_PATH, { replace: true })
    })
    return () => {
      unsubscribePassword()
      unsubscribeTotp()
    }
  }, [navigate, refreshProfile])

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
      profileError,
      login,
      logout,
      refreshProfile,
      replaceToken,
      can,
    }),
    [token, me, loadingProfile, profileError, login, logout, refreshProfile, replaceToken, can],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
