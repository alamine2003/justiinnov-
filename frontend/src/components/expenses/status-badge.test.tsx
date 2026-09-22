/**
 * Régression : les couleurs de statut étaient des teintes Tailwind brutes,
 * identiques dans les deux thèmes. Sur fond sombre, le texte blanc des badges
 * passait sous le seuil de contraste.
 */
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { StatusBadge } from "@/components/expenses/status-badge"
import {
  ACTION_STYLE,
  ALERT_LEVEL_STYLE,
  PROJECT_STYLE,
  PROOF_STYLE,
  REALLOCATION_STYLE,
  WORKFLOW_STYLE,
} from "@/lib/status-styles"
import type { ProofStatus, WorkflowStatus } from "@/lib/types"

/**
 * Teintes Tailwind brutes et blanc en dur : interdits par DESIGN.md.
 *
 * La liste couvre désormais toutes les familles de Tailwind : elle n'en
 * nommait que dix, si bien qu'un `text-sky-600` ou un `bg-rose-500` serait
 * passé. Les préfixes `fill-` et `stroke-` sont ajoutés pour les graphiques.
 */
const TEINTE_BRUTE =
  /\b(?:bg|text|border|fill|stroke|ring|from|via|to)-(?:red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|slate|gray|zinc|neutral|stone)-\d{2,3}\b|\b(?:text|bg|border|fill|stroke|shadow)-(?:white|black)\b/

/**
 * Une comparaison de statut dans un composant ou une page : la teinte d'une
 * carte, ou une règle du circuit, qui devrait vivre dans `lib/`
 * (`status-styles.ts` pour la première, `circuit.ts` pour la seconde).
 */
const COMPARAISON_STATUT = /\.status\s*(?:===|!==)\s*["']/

function fichiersSource(dossier: string): string[] {
  return readdirSync(dossier).flatMap((nom) => {
    const chemin = join(dossier, nom)
    if (statSync(chemin).isDirectory()) return fichiersSource(chemin)
    return /\.(tsx?|css)$/.test(nom) && !nom.endsWith(".test.tsx") && !nom.endsWith(".test.ts")
      ? [chemin]
      : []
  })
}

describe("StatusBadge", () => {
  it("chaque statut du workflow a une couleur", () => {
    const statuses: WorkflowStatus[] = [
      "draft", "submitted", "in_review", "justified", "unjustified", "closed",
    ]

    expect(Object.keys(WORKFLOW_STYLE)).toEqual(expect.arrayContaining(statuses))
    expect(Object.keys(WORKFLOW_STYLE)).toHaveLength(statuses.length)
  })

  it("chaque statut de justificatif a une couleur", () => {
    const statuses: ProofStatus[] = [
      "received", "incomplete", "to_review", "validated", "rejected", "archived",
    ]

    expect(Object.keys(PROOF_STYLE)).toEqual(expect.arrayContaining(statuses))
    expect(Object.keys(PROOF_STYLE)).toHaveLength(statuses.length)
  })

  it("aucune teinte Tailwind brute ne subsiste dans les tables de style", () => {
    const tables = [
      WORKFLOW_STYLE, PROOF_STYLE, PROJECT_STYLE,
      REALLOCATION_STYLE, ALERT_LEVEL_STYLE, ACTION_STYLE,
    ]

    for (const table of tables) {
      expect(Object.values(table).some((value) => TEINTE_BRUTE.test(value))).toBe(false)
    }
  })

  it("aucune couleur en dur ne subsiste dans src/", () => {
    // Le texte d'un badge « rejeté » était blanc en dur, illisible sur le
    // rouge atténué du thème sombre ; une icône « approuver » était en
    // `text-emerald-600`, hors palette ; le voile d'un dialogue était en
    // `bg-black/10`, invisible sur le fond sombre. Un grep échoue désormais
    // au test.
    const fautifs = fichiersSource(join(import.meta.dirname, "../../")).filter((chemin) =>
      TEINTE_BRUTE.test(readFileSync(chemin, "utf8")),
    )

    expect(fautifs).toEqual([])
  })

  it("aucune comparaison de statut ne subsiste hors de lib/", () => {
    // La carte d'une ligne en contrôle prenait sa teinte d'un
    // `expense.status === "in_review"` écrit dans le composant, et celle
    // d'une réallocation d'un `row.status === "pending"` dans un autre :
    // deux endroits où ajouter un statut, en plus de `status-styles.ts`.
    const racine = join(import.meta.dirname, "../../")
    const fautifs = fichiersSource(racine)
      .filter((chemin) => !chemin.startsWith(join(racine, "lib")))
      .filter((chemin) => COMPARAISON_STATUT.test(readFileSync(chemin, "utf8")))

    expect(fautifs).toEqual([])
  })

  it("le libellé français est affiché", () => {
    render(<StatusBadge status="justified" />)

    expect(screen.getByText("Justifié")).toBeInTheDocument()
  })

  it("préfère le libellé du serveur quand il est fourni", () => {
    render(<StatusBadge status="justified" label="Justifiée" />)

    expect(screen.getByText("Justifiée")).toBeInTheDocument()
  })
})

// ---------------------------------------------------------------------------
// Contraste des paires de statut
// ---------------------------------------------------------------------------

/** Convertit une couleur `oklch(L C H)` d'`index.css` en sRGB linéaire borné au gamut. */
function oklchEnLineaire(couleur: string): [number, number, number] {
  const [clarte, chroma, teinte] = couleur
    .replace(/oklch\(|\)/g, "")
    .trim()
    .split(/\s+/)
    .map(Number)
  const radians = (teinte * Math.PI) / 180
  const a = chroma * Math.cos(radians)
  const b = chroma * Math.sin(radians)
  const l = (clarte + 0.3963377774 * a + 0.2158037573 * b) ** 3
  const m = (clarte - 0.1055613458 * a - 0.0638541728 * b) ** 3
  const s = (clarte - 0.0894841775 * a - 1.291485548 * b) ** 3
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ].map((canal) => Math.min(Math.max(canal, 0), 1)) as [number, number, number]
}

/** Rapport de contraste WCAG entre deux couleurs `oklch`. */
function contraste(fond: string, texte: string): number {
  const luminance = (couleur: string) => {
    const [r, v, b] = oklchEnLineaire(couleur)
    return 0.2126 * r + 0.7152 * v + 0.0722 * b
  }
  const [clair, sombre] = [luminance(fond), luminance(texte)].sort((x, y) => y - x)
  return (clair + 0.05) / (sombre + 0.05)
}

/** Valeurs des variables CSS d'un bloc (`:root` ou `.dark`) d'`index.css`. */
function jetons(bloc: ":root" | ".dark"): Record<string, string> {
  const css = readFileSync(join(import.meta.dirname, "../../index.css"), "utf8")
  const corps = new RegExp(`^${bloc.replace(".", "\\.")} \\{([\\s\\S]*?)^\\}`, "m").exec(css)
  if (!corps) throw new Error(`bloc ${bloc} introuvable dans index.css`)
  return Object.fromEntries(
    [...corps[1].matchAll(/^\s*(--[\w-]+):\s*(oklch\([^)]*\));/gm)].map((m) => [m[1], m[2]]),
  )
}

/**
 * Chaque teinte de statut doit se lire sur son encre. Les badges sont en
 * `text-xs` : le seuil applicable est celui du texte normal, 4,5:1.
 *
 * Régression : l'émeraude du succès donnait 2,47:1, le bleu de l'information
 * 3,76:1 et l'azur de la marque 3,10:1 — du blanc en dur par le jeton, que le
 * grep sur `text-white` ne pouvait pas voir. DESIGN.md affirmait pourtant que
 * le contraste était garanti dans les deux thèmes.
 */
describe("contraste des jetons", () => {
  const PAIRES: [string, string, string][] = [
    ["--statut-succes", "--statut-succes-foreground", "badge justifie"],
    ["--statut-attente", "--statut-attente-foreground", "badge en controle"],
    ["--statut-info", "--statut-info-foreground", "badge soumis"],
    ["--statut-neutre", "--statut-neutre-foreground", "badge brouillon"],
    ["--statut-archive", "--statut-archive-foreground", "badge cloture"],
    ["--destructive", "--destructive-foreground", "badge non justifie"],
    ["--marque", "--marque-foreground", "azur de la marque"],
    ["--marque-fort", "--marque-fort-foreground", "azur fort"],
    ["--banniere", "--banniere-foreground", "bandeau marine"],
    ["--banniere", "--banniere-muted", "bandeau, etiquette"],
  ]

  it.each([":root", ".dark"] as const)("atteint 4,5:1 sur chaque paire en %s", (bloc) => {
    const table = jetons(bloc)
    const faibles = PAIRES.filter(([fond, texte]) => contraste(table[fond], table[texte]) < 4.5).map(
      ([fond, texte, nom]) =>
        `${nom} (${fond}/${texte}) : ${contraste(table[fond], table[texte]).toFixed(2)}:1`,
    )

    expect(faibles).toEqual([])
  })
})
