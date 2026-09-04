import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react"
import {
  applyTheme,
  readStoredTheme,
  resolveTheme,
  storeTheme,
  type ResolvedTheme,
  type Theme,
} from "@/lib/theme"
import { ThemeContext } from "@/context/theme-context"

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => readStoredTheme())
  // Préférence du système, suivie en direct : `resolved` en dépend quand le
  // choix est « système », et l'icône du sélecteur doit changer avec elle.
  const [systemDark, setSystemDark] = useState(() => resolveTheme("system") === "dark")
  const resolved: ResolvedTheme =
    theme === "system" ? (systemDark ? "dark" : "light") : theme

  useEffect(() => {
    applyTheme(resolved)
  }, [resolved])

  useEffect(() => {
    const media = window.matchMedia?.("(prefers-color-scheme: dark)")
    if (!media) return

    const handleChange = (event: MediaQueryListEvent | MediaQueryList) =>
      setSystemDark(event.matches)
    if (media.addEventListener) {
      media.addEventListener("change", handleChange)
    } else {
      media.addListener?.(handleChange)
    }

    // Sans abonnement, un changement de thème système en soirée resterait
    // clair jusqu'au prochain rechargement de l'application.
    return () => {
      if (media.removeEventListener) {
        media.removeEventListener("change", handleChange)
      } else {
        media.removeListener?.(handleChange)
      }
    }
  }, [])

  const setTheme = useCallback((nextTheme: Theme) => {
    setThemeState(nextTheme)
    storeTheme(nextTheme)
  }, [])

  const value = useMemo(
    () => ({ theme, resolved, setTheme }),
    [theme, resolved, setTheme],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
