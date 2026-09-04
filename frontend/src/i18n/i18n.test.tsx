/**
 * Garde-fous de l'internationalisation :
 * - les deux langues ont exactement les mêmes clés ;
 * - l'application se rend bien en anglais ;
 * - aucune chaîne française n'est restée en dur dans le code.
 */
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join, relative } from "node:path"
import { act, cleanup, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n"
import en from "@/i18n/en.json"
import fr from "@/i18n/fr.json"
import { ThemeProvider } from "@/context/theme"
import { LoginPage } from "@/pages/login"

vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({
    isAuthenticated: false,
    login: vi.fn(),
  }),
}))

type Arbre = { [cle: string]: string | Arbre }

function cles(arbre: Arbre, prefixe = ""): string[] {
  return Object.entries(arbre).flatMap(([cle, valeur]) => {
    const chemin = prefixe ? `${prefixe}.${cle}` : cle
    return typeof valeur === "object" && valeur !== null ? cles(valeur, chemin) : [chemin]
  })
}

describe("fr.json et en.json", () => {
  it("ont exactement les mêmes clés", () => {
    const clesFr = cles(fr as Arbre).sort()
    const clesEn = cles(en as Arbre).sort()

    expect(clesEn).toEqual(clesFr)
  })

  it("n'ont aucune valeur vide", () => {
    const vides = (arbre: Arbre) =>
      cles(arbre).filter((chemin) => {
        const valeur = chemin.split(".").reduce<unknown>((noeud, cle) => (noeud as Arbre)[cle], arbre)
        return typeof valeur !== "string" || valeur.trim() === ""
      })

    expect(vides(fr as Arbre)).toEqual([])
    expect(vides(en as Arbre)).toEqual([])
  })
})

/** Change la langue sur des composants montés : un rendu React s'ensuit. */
async function changerLangue(langue: "fr" | "en") {
  await act(() => i18n.changeLanguage(langue))
}

describe("langue anglaise", () => {
  afterEach(async () => {
    cleanup()
    await changerLangue("fr")
  })

  it("rend l'écran de connexion en anglais et met <html lang> à jour", async () => {
    await changerLangue("en")

    render(
      <ThemeProvider>
        <MemoryRouter>
          <LoginPage />
        </MemoryRouter>
      </ThemeProvider>,
    )

    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument()
    expect(screen.getByLabelText("Username")).toBeInTheDocument()
    expect(document.documentElement.lang).toBe("en")
  })

  it("revient au français", async () => {
    await changerLangue("en")
    await changerLangue("fr")

    render(
      <ThemeProvider>
        <MemoryRouter>
          <LoginPage />
        </MemoryRouter>
      </ThemeProvider>,
    )

    expect(screen.getByRole("heading", { name: "Connexion" })).toBeInTheDocument()
    expect(document.documentElement.lang).toBe("fr")
  })
})

// ---------------------------------------------------------------------------
// Chaînes en dur
// ---------------------------------------------------------------------------

/** Lettres accentuées du français : une chaîne qui en contient n'a pas été traduite. */
const ACCENT = /[àâäéèêëîïôöùûüçœÀÂÄÉÈÊËÎÏÔÖÙÛÜÇŒ]/

/**
 * Fichiers où une chaîne accentuée est tolérée, avec la raison. À garder
 * court : chaque entrée est une chaîne que l'utilisateur ne verra jamais.
 */
const LISTE_BLANCHE: Record<string, string> = {
  "context/use-auth.ts": "exception réservée au développeur (hook hors provider), jamais affichée",
  "context/use-theme.ts": "exception réservée au développeur (hook hors provider), jamais affichée",
}

function fichiersSource(dossier: string): string[] {
  return readdirSync(dossier).flatMap((nom) => {
    const chemin = join(dossier, nom)
    if (statSync(chemin).isDirectory()) {
      // `i18n/` porte les traductions ; `test/` la configuration des tests.
      return ["i18n", "test"].includes(nom) ? [] : fichiersSource(chemin)
    }
    return /\.tsx?$/.test(nom) && !/\.test\.tsx?$/.test(nom) && !nom.endsWith(".d.ts")
      ? [chemin]
      : []
  })
}

/**
 * Retire les commentaires, en français par convention, pour ne juger que le
 * code. Les sauts de ligne d'un bloc sont conservés : les numéros de ligne
 * signalés restent ceux du fichier.
 */
function sansCommentaires(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (bloc) => bloc.replace(/[^\n]/g, ""))
    .replace(/(^|[^:"'`\\])\/\/.*$/gm, "$1")
}

describe("chaînes françaises en dur", () => {
  it("aucune ne subsiste dans src/ hors commentaires", () => {
    const racine = join(import.meta.dirname, "..")
    const fautifs: string[] = []

    for (const chemin of fichiersSource(racine)) {
      const relatif = relative(racine, chemin)
      if (relatif in LISTE_BLANCHE) continue
      const lignes = sansCommentaires(readFileSync(chemin, "utf8")).split("\n")
      lignes.forEach((ligne, index) => {
        if (ACCENT.test(ligne)) fautifs.push(`${relatif}:${index + 1}: ${ligne.trim()}`)
      })
    }

    expect(fautifs).toEqual([])
  })

  it("la liste blanche ne couvre que des fichiers existants qui en ont besoin", () => {
    const racine = join(import.meta.dirname, "..")
    for (const relatif of Object.keys(LISTE_BLANCHE)) {
      const source = sansCommentaires(readFileSync(join(racine, relatif), "utf8"))
      expect(ACCENT.test(source), `${relatif} n'a plus besoin d'être en liste blanche`).toBe(true)
    }
  })
})
