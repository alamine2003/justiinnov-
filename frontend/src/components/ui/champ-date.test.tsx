import { readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"
import { useState } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ChampDate } from "./champ-date"
import { Label } from "./label"

function Monte({
  initiale = "",
  effacable = false,
  surChangement = vi.fn(),
}: {
  initiale?: string
  effacable?: boolean
  surChangement?: (valeur: string) => void
}) {
  const [valeur, setValeur] = useState(initiale)
  return (
    <>
      <Label htmlFor="date-essai">Date d'effet</Label>
      <ChampDate
        id="date-essai"
        value={valeur}
        effacable={effacable}
        onChange={(v) => {
          setValeur(v)
          surChangement(v)
        }}
      />
    </>
  )
}

describe("ChampDate", () => {
  it("est nommé par son libellé et montre la date en clair", () => {
    render(<Monte initiale="2026-11-11" />)

    const champ = screen.getByRole("button", { name: /Date d'effet/ })
    expect(champ).toHaveTextContent("11 nov. 2026")
  })

  it("invite à choisir quand il est vide", () => {
    render(<Monte />)

    expect(screen.getByRole("button", { name: /Date d'effet/ })).toHaveTextContent("Choisir une date")
  })

  it("rend « AAAA-MM-JJ » en heure locale, comme le champ natif", async () => {
    const surChangement = vi.fn()
    render(<Monte initiale="2026-11-11" surChangement={surChangement} />)

    fireEvent.click(screen.getByRole("button", { name: /Date d'effet/ }))
    fireEvent.click(await screen.findByRole("button", { name: /20 novembre 2026/ }))

    expect(surChangement).toHaveBeenCalledWith("2026-11-20")
    expect(screen.getByRole("button", { name: /Date d'effet/ })).toHaveTextContent("20 nov. 2026")
  })

  it("s'ouvre sur le mois de la date choisie, en français", async () => {
    render(<Monte initiale="2025-03-15" />)

    fireEvent.click(screen.getByRole("button", { name: /Date d'effet/ }))

    expect(await screen.findByRole("grid", { name: /mars 2025/ })).toBeInTheDocument()
  })

  it("efface la date d'un filtre", async () => {
    const surChangement = vi.fn()
    render(<Monte initiale="2026-11-11" effacable surChangement={surChangement} />)

    fireEvent.click(screen.getByRole("button", { name: /Date d'effet/ }))
    fireEvent.click(await screen.findByRole("button", { name: "Effacer la date" }))

    expect(surChangement).toHaveBeenCalledWith("")
    expect(screen.getByRole("button", { name: /Date d'effet/ })).toHaveTextContent("Choisir une date")
  })

  it("ne propose pas d'effacer un champ obligatoire", async () => {
    render(<Monte initiale="2026-11-11" />)

    fireEvent.click(screen.getByRole("button", { name: /Date d'effet/ }))

    expect(await screen.findByRole("grid")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Effacer la date" })).toBeNull()
  })
})

/**
 * Le sélecteur natif est dessiné par le navigateur (minuscule sous Safari,
 * dans sa langue à lui) : une date se saisit par `ChampDate`. Seul reste le
 * champ date et heure de la saisie d'une dépense, que traversent les guides
 * vidéo — il changera avec leur nouveau tournage.
 */
describe("aucun sélecteur de date natif", () => {
  const TOLERES = new Set([join("components", "expenses", "expense-form.tsx")])

  function fichiers(dossier: string): string[] {
    return readdirSync(dossier).flatMap((nom) => {
      const chemin = join(dossier, nom)
      if (statSync(chemin).isDirectory()) return fichiers(chemin)
      return chemin.endsWith(".tsx") && !chemin.endsWith(".test.tsx") ? [chemin] : []
    })
  }

  it("ni date, ni mois, ni date et heure hors des exceptions nommées", () => {
    const racine = join(__dirname, "..", "..")
    const fautifs = fichiers(racine)
      .filter((chemin) => /type="(date|month|datetime-local)"/.test(readFileSync(chemin, "utf8")))
      .map((chemin) => chemin.slice(racine.length + 1))
      .filter((chemin) => !TOLERES.has(chemin))
    expect(fautifs).toEqual([])
  })
})
