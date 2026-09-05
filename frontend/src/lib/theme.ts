/**
 * Choix de thème, et sa résolution en apparence effective.
 *
 * Le choix vit dans le navigateur : il est propre à l'appareil, ne dépend pas
 * du compte et n'a aucune raison de transiter par le serveur.
 */

/** Ce que la personne a choisi. */
export type Theme = "light" | "dark" | "system"

/** Ce qui est réellement appliqué à la page. */
export type ResolvedTheme = "light" | "dark"

const THEME_STORAGE_KEY = "justi_theme"

export const THEMES: Theme[] = ["light", "dark", "system"]

export function readStoredTheme(): Theme {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY)
    return stored && THEMES.includes(stored as Theme) ? (stored as Theme) : "system"
  } catch {
    return "system"
  }
}

export function storeTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    // Un échec d'écriture n'empêche pas le thème de s'appliquer pour la session.
  }
}

function systemTheme(): ResolvedTheme {
  if (!window.matchMedia) {
    return "light"
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light"
}

export function resolveTheme(theme: Theme): ResolvedTheme {
  return theme === "system" ? systemTheme() : theme
}

export function applyTheme(resolved: ResolvedTheme): void {
  const racine = document.documentElement
  racine.classList.toggle("dark", resolved === "dark")
  racine.style.colorScheme = resolved
}
