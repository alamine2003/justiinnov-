/**
 * Les primitives graphiques traduisent des montants en longueurs. Ce qui est
 * vérifié ici, c'est cette traduction — et surtout les cas où elle pourrait
 * mentir : un dépassement qui déborderait du cadre, un diviseur nul, un
 * brouillon qui se lirait comme un écart total.
 */
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import {
  BarreEcart,
  BarreEnveloppe,
  CourbeMensuelle,
  Jauge,
  RailEnveloppe,
} from "@/components/ui/charts"

/** Largeur d'un segment, telle qu'elle a été posée en style en ligne. */
function largeurs(conteneur: HTMLElement): string[] {
  return [...conteneur.querySelectorAll<HTMLElement>("div[style*='width']")].map(
    (noeud) => noeud.style.width,
  )
}

describe("BarreEnveloppe", () => {
  it("garde le dépassement dans le cadre et le teinte en destructif", () => {
    const { container } = render(
      <BarreEnveloppe consumed={130} engaged={0} allocated={100} scale={200} title="CI" />,
    )

    // Consommé plafonné à l'enveloppe (50 % de l'échelle), dépassement de 30
    // posé après le trait (15 %) : la somme ne sort jamais des 100 %.
    expect(largeurs(container)).toContain("50%")
    expect(largeurs(container)).toContain("15%")
    expect(container.querySelector(".bg-destructive")).not.toBeNull()
  })

  it("n'ouvre aucun segment destructif sans dépassement", () => {
    const { container } = render(
      <BarreEnveloppe consumed={40} engaged={10} allocated={100} scale={100} title="TG" />,
    )

    expect(container.querySelector(".bg-destructive")).toBeNull()
  })

  it("empêche l'engagé de franchir l'enveloppe", () => {
    const { container } = render(
      <BarreEnveloppe consumed={90} engaged={50} allocated={100} scale={100} title="SN" />,
    )

    // L'engagé se pose sur les dix qui restent, pas sur les cinquante demandés.
    expect(largeurs(container)).toContain("10%")
  })

  it("compte l'engagé dans le dépassement, comme le serveur", () => {
    // Régression : le dépassement se mesurait sur le seul consommé. Avec
    // attribué 100, consommé 80 et engagé 40, le serveur rend
    // `remaining = -20` et `execution_rate = 1,20` — mais la barre s'arrêtait
    // pile au plafond, sans segment corail : le dessin démentait le chiffre.
    const { container } = render(
      <BarreEnveloppe consumed={80} engaged={40} allocated={100} scale={120} title="TG" />,
    )

    expect(container.querySelector(".bg-destructive")).not.toBeNull()
  })

  it("ne laisse pas le dépassement sortir du cadre", () => {
    const { container } = render(
      <BarreEnveloppe consumed={90} engaged={90} allocated={100} scale={100} title="SN" />,
    )

    const debordent = [...container.querySelectorAll<HTMLElement>("div[style*='width']")].filter(
      (noeud) =>
        parseFloat(noeud.style.left || "0") + parseFloat(noeud.style.width || "0") > 100.01,
    )
    expect(debordent).toEqual([])
  })

  it("ne divise pas par une échelle nulle", () => {
    const { container } = render(
      <BarreEnveloppe consumed={0} engaged={0} allocated={0} scale={0} title="Sans enveloppe" />,
    )

    expect(largeurs(container).every((valeur) => valeur === "0%")).toBe(true)
  })

  it("dit aux lecteurs d'écran ce que la barre montre", () => {
    render(
      <BarreEnveloppe consumed={1} engaged={0} allocated={2} scale={2} title="Togo a 50 %" />,
    )

    expect(screen.getByText("Togo a 50 %")).toBeInTheDocument()
  })
})

describe("RailEnveloppe", () => {
  it("gradue chaque seuil à sa place", () => {
    const { container } = render(
      <RailEnveloppe
        consumed={80}
        engaged={5}
        justified={70}
        allocated={100}
        thresholds={[80, 90, 100]}
        thresholdLabels={["80 %", "90 %", "100 %"]}
        title="Togo"
      />,
    )

    const positions = [...container.querySelectorAll<HTMLElement>("div[style*='left']")].map(
      (noeud) => noeud.style.left,
    )
    expect(positions).toEqual(expect.arrayContaining(["80%", "90%", "100%"]))
    expect(screen.getByText("90 %")).toBeInTheDocument()
  })

  it("ne pousse pas un seuil au-delà du rail", () => {
    const { container } = render(
      <RailEnveloppe
        consumed={10}
        engaged={0}
        justified={10}
        allocated={100}
        thresholds={[150]}
        thresholdLabels={["150 %"]}
        title="Hors cadre"
      />,
    )

    const positions = [...container.querySelectorAll<HTMLElement>("div[style*='left']")].map(
      (noeud) => noeud.style.left,
    )
    expect(positions).toContain("100%")
    expect(positions).not.toContain("150%")
  })
})

describe("BarreEcart", () => {
  it("partage la barre entre le justifié et l'écart", () => {
    const { container } = render(<BarreEcart amount={1000} justified={750} title="Hotel" />)

    expect(largeurs(container)).toEqual(["75%", "25%"])
  })

  it("ne montre aucun écart quand tout est justifié", () => {
    const { container } = render(<BarreEcart amount={500} justified={500} title="Carburant" />)

    expect(largeurs(container)).toEqual(["100%", "0%"])
  })
})

describe("Jauge", () => {
  it("affiche le taux du serveur au centre", () => {
    render(<Jauge rate="0.951" label="95,1 %" title="Equipe commerciale" />)

    expect(screen.getByText("95,1 %")).toBeInTheDocument()
    expect(screen.getByText("Equipe commerciale")).toBeInTheDocument()
  })

  it("passe en teinte destructive au-delà du plafond", () => {
    const { container } = render(
      <Jauge rate="1.042" label="104,2 %" over title="Cote d'Ivoire" />,
    )

    expect(container.querySelector(".stroke-destructive")).not.toBeNull()
  })

  it("supporte un taux absent", () => {
    render(<Jauge rate={null} label="—" title="Sans consommation" />)

    expect(screen.getByText("—")).toBeInTheDocument()
  })
})

describe("CourbeMensuelle", () => {
  const douze = Array.from({ length: 12 }, (_, index) => ({
    month: index + 1,
    amount: (index + 1) * 1_000_000,
    justified: index * 900_000,
  }))

  it("gradue les douze mois", () => {
    const { container } = render(<CourbeMensuelle points={douze} title="Consommation" />)

    // Douze noms de mois, plus les cinq graduations de l'axe des montants.
    expect(container.querySelectorAll("text")).toHaveLength(17)
    expect(screen.getByText("Consommation")).toBeInTheDocument()
  })

  it("dessine un exercice entièrement vide sans produire de coordonnée invalide", () => {
    const vide = Array.from({ length: 12 }, (_, index) => ({
      month: index + 1,
      amount: 0,
      justified: 0,
    }))
    const { container } = render(<CourbeMensuelle points={vide} title="Aucune dépense" />)

    const traces = [...container.querySelectorAll("path")].map((noeud) =>
      noeud.getAttribute("d") ?? "",
    )
    expect(traces.length).toBeGreaterThan(0)
    expect(traces.some((trace) => trace.includes("NaN"))).toBe(false)
  })
})
