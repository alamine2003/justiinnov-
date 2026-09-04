import { createContext } from "react"
import type { ResolvedTheme, Theme } from "@/lib/theme"

export interface ThemeContextValue {
  /** Choix de la personne : « clair », « sombre » ou « système ». */
  theme: Theme
  /** Apparence réellement appliquée, « système » déjà résolu. */
  resolved: ResolvedTheme
  setTheme: (theme: Theme) => void
}

export const ThemeContext = createContext<ThemeContextValue | null>(null)
