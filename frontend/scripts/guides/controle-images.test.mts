import type { Page } from "playwright"
import { afterEach, describe, expect, it, vi } from "vitest"

import {
  DECALAGES_DU_CONTROLE,
  SEUIL_D_ECART,
  SEUIL_DE_NIVEAU,
  ecartSurLaFenetre,
  ecartsExcessifs,
  echecDuControle,
  instantsDuControle,
  pourcentage,
  proportionDifferente,
  typeDImage,
  type Ecart,
} from "./controle-images.ts"
import { DELAI_DE_LA_CAPTURE, Scene, tempsDeLecture } from "./scene.ts"

/** Une image RGBA de `n` pixels, tous de la même couleur. */
function uni(n: number, [r, g, b]: [number, number, number]) {
  return Array.from({ length: n }, () => [r, g, b, 255]).flat()
}

describe("proportionDifferente", () => {
  it("vaut zéro entre deux images identiques", () => {
    expect(proportionDifferente(uni(8, [10, 20, 30]), uni(8, [10, 20, 30]))).toBe(0)
  })

  it("compte les pixels dont une composante s'écarte au-delà du seuil de niveau", () => {
    const a = uni(4, [100, 100, 100])
    const b = [...a]
    b[4 * 2 + 1] = 100 + SEUIL_DE_NIVEAU + 1 // le vert du troisième pixel
    expect(proportionDifferente(a, b)).toBe(0.25)
  })

  it("ne compte pas un écart égal au seuil, ni l'opacité", () => {
    const a = uni(2, [100, 100, 100])
    const b = [...a]
    b[0] = 100 + SEUIL_DE_NIVEAU
    b[7] = 0 // l'opacité du second pixel
    expect(proportionDifferente(a, b)).toBe(0)
  })

  it("refuse des images de tailles différentes ou vides", () => {
    expect(() => proportionDifferente(uni(2, [0, 0, 0]), uni(3, [0, 0, 0]))).toThrow("tailles différentes")
    expect(() => proportionDifferente([], [])).toThrow("RGBA invalide")
  })
})

describe("fenêtre de contrôle", () => {
  it("commence 0,4 s après le début du sous-titre, et ne dépasse pas une seconde", () => {
    // Le sous-titre 7 de la prise fautive commençait à 35,579 s.
    const instants = instantsDuControle({ debut: 35_579, texte: "Le projet est ouvert" })
    expect(instants[0]).toBe(35_979)
    expect(Math.max(...DECALAGES_DU_CONTROLE)).toBeLessThanOrEqual(1000)
    // La capture précède la première image contrôlée : elle montre l'écran
    // que le sous-titre doit avoir à l'image.
    expect(DELAI_DE_LA_CAPTURE).toBeLessThan(DECALAGES_DU_CONTROLE[0])
    // Une légende dure au moins 2,5 s : la fenêtre n'atteint pas le geste suivant.
    expect(Math.max(...DECALAGES_DU_CONTROLE)).toBeLessThan(tempsDeLecture(""))
  })

  it("s'arrête à la première image assez proche : une seule extraction pour une prise juste", async () => {
    const mesurer = vi.fn(async () => 0.001)
    expect(await ecartSurLaFenetre([400, 550, 700], mesurer)).toBe(0.001)
    expect(mesurer).toHaveBeenCalledTimes(1)
  })

  it("tolère une vidéo en retard de quelques dixièmes au début d'une prise", async () => {
    const ecarts: Record<number, number> = { 400: 0.034, 550: 0.0002 }
    const mesurer = vi.fn(async (instant: number) => ecarts[instant] ?? 1)
    expect(await ecartSurLaFenetre([400, 550, 700], mesurer)).toBe(0.0002)
    expect(mesurer).toHaveBeenCalledTimes(2)
  })

  it("retient le plus petit écart d'une prise figée sur toute la fenêtre", async () => {
    const mesurer = vi.fn(async (instant: number) => (instant === 700 ? 0.06 : 0.062))
    expect(await ecartSurLaFenetre([400, 550, 700, 850], mesurer)).toBe(0.06)
    expect(mesurer).toHaveBeenCalledTimes(4)
  })
})

describe("seuil et message d'échec", () => {
  it("se tient entre le bruit et la prise fautive de la 2.1.0 (calibration de la décision 118)", () => {
    // Mesures à 320 × 200 et 32 niveaux : même écran, affiche contre vidéo,
    // au plus 0,15 % ; fr/ouvrir-un-projet, sous-titre 7, 6,24 %. Relever
    // le seuil au-dessus de la moitié de la prise fautive la laisserait
    // passer de justesse ; le baisser près du bruit ferait échouer des
    // prises justes.
    const bruitMesure = 0.0015
    const priseFautive = 0.0624
    expect(SEUIL_D_ECART).toBeGreaterThan(bruitMesure * 10)
    expect(SEUIL_D_ECART).toBeLessThan(priseFautive / 2)
  })

  it("ne retient que les sous-titres au-delà du seuil", () => {
    const ecarts: Ecart[] = [
      { numero: 1, texte: "a", instant: 1_900, ecart: 0 },
      { numero: 7, texte: "b", instant: 35_979, ecart: SEUIL_D_ECART + 0.001 },
      { numero: 8, texte: "c", instant: 40_000, ecart: SEUIL_D_ECART },
    ]
    expect(ecartsExcessifs(ecarts).map((e) => e.numero)).toEqual([7])
  })

  it("nomme le guide, le sous-titre, l'instant et l'écart, et dit que rien n'est copié", () => {
    const erreur = echecDuControle("fr/ouvrir-un-projet", [
      { numero: 7, texte: "Le projet est ouvert : il a sa référence et ses dossiers, un par type.", instant: 35_979, ecart: 0.0624 },
    ])
    expect(erreur.message).toContain("Images de fr/ouvrir-un-projet")
    expect(erreur.message).toContain("sous-titre 7 (00:00:35.979) « Le projet est ouvert")
    expect(erreur.message).toContain("6,2 % des pixels diffèrent")
    expect(erreur.message).toContain(`seuil ${pourcentage(SEUIL_D_ECART)}`)
    expect(erreur.message).toContain("rien n'est copié dans public/guides")
  })

  it("reconnaît le PNG et le JPEG à leurs premiers octets", () => {
    expect(typeDImage(new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d]))).toBe("image/png")
    expect(typeDImage(new Uint8Array([0xff, 0xd8, 0xff]))).toBe("image/jpeg")
    expect(() => typeDImage(new Uint8Array([0x1a, 0x45]))).toThrow("ni PNG ni JPEG")
  })
})

describe("Scene.dire capture la page sous chaque sous-titre", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  /** Une page factice : le temps avance quand on l'attend, chaque capture est numérotée. */
  function pageFactice() {
    let horloge = 0
    const attentes: number[] = []
    const captures: { type?: string; caret?: string }[] = []
    vi.spyOn(Date, "now").mockImplementation(() => horloge)
    const page = {
      waitForTimeout: vi.fn(async (ms: number) => {
        attentes.push(ms)
        horloge += ms
      }),
      screenshot: vi.fn(async (options: { type?: string; caret?: string }) => {
        captures.push(options)
        horloge += 120 // une capture prend du temps
        return Buffer.from([0x89, 0x50, 0x4e, 0x47, captures.length])
      }),
    }
    return { page: page as unknown as Page, attentes, captures }
  }

  it("prend une capture PNG par légende, après le délai, sans rallonger la légende", async () => {
    const { page, attentes, captures } = pageFactice()
    const legendes = ["Cliquez sur « Créer ».", "Le projet est ouvert."]
    const scene = new Scene(page, legendes)
    await scene.dire(0)
    await scene.dire(1)

    expect(scene.reperes.map((r) => r.texte)).toEqual(legendes)
    expect(scene.captures).toHaveLength(2)
    expect(scene.captures[1][4]).toBe(2)
    expect(captures).toEqual([
      { type: "png", caret: "initial" },
      { type: "png", caret: "initial" },
    ])
    // Délai, capture (120 ms), puis le reste du temps de lecture : la
    // légende suivante commence exactement après le temps de lecture.
    expect(attentes.slice(0, 2)).toEqual([DELAI_DE_LA_CAPTURE, tempsDeLecture(legendes[0]) - DELAI_DE_LA_CAPTURE - 120])
    expect(scene.reperes[1].debut - scene.reperes[0].debut).toBe(tempsDeLecture(legendes[0]))
  })
})
