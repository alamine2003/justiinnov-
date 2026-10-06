/**
 * Les fichiers des guides vidéo, tels qu'ils partent dans l'image du
 * frontend (décision 118). Le catalogue (`guides.ts`) et
 * `public/guides/` n'étaient rapprochés par rien : un `.vtt` perdu, une
 * langue non commitée, un guide ajouté sans tournage passaient la CI, et le
 * manager voyait un lecteur vide ou une vidéo sans sous-titres. Les
 * captures (`scripts/screenshot.ts`) n'ouvrent que le premier guide
 * français ; ce test lit le disque, pour tous les guides et toutes les
 * langues.
 *
 * Il tient aussi le budget de poids : les vidéos vivent dans git et dans
 * l'image, sans Git LFS (décision 118), et chaque tournage les ajoute à
 * l'historique pour toujours.
 */
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import { GUIDES, LANGUES_DES_GUIDES } from "./guides"

const DOSSIER = join(process.cwd(), "public", "guides")

/** Le poids maximal de `public/guides/`, en octets (décision 118 : 5,8 Mo mesurés en 2.1.0). */
const BUDGET_EN_OCTETS = 6_000_000

/**
 * Les trois fichiers d'un guide, chacun avec la signature qui ouvre un
 * fichier de ce type : un fichier tronqué ou d'un autre format ne passe pas
 * pour une vidéo.
 */
const SIGNATURES = {
  // En-tête EBML de Matroska, dont WebM est un profil.
  webm: (contenu: Buffer) => contenu.subarray(0, 4).equals(Buffer.from([0x1a, 0x45, 0xdf, 0xa3])),
  // La spécification WebVTT ouvre le fichier par « WEBVTT », après une éventuelle marque d'ordre des octets.
  vtt: (contenu: Buffer) => /^(﻿)?WEBVTT(?:[ \t\n]|\r|$)/.test(contenu.toString("utf8")),
  jpg: (contenu: Buffer) => contenu[0] === 0xff && contenu[1] === 0xd8,
} as const

const EXTENSIONS = Object.keys(SIGNATURES) as (keyof typeof SIGNATURES)[]

const ATTENDUS = LANGUES_DES_GUIDES.flatMap((langue) =>
  GUIDES.flatMap((guide) => EXTENSIONS.map((extension) => join(langue, `${guide.id}.${extension}`))),
)

/** Tous les fichiers sous `public/guides/`, en chemins relatifs. */
function fichiersPresents(dossier = DOSSIER, prefixe = ""): string[] {
  return readdirSync(dossier, { withFileTypes: true }).flatMap((entree) =>
    entree.isDirectory()
      ? fichiersPresents(join(dossier, entree.name), join(prefixe, entree.name))
      : [join(prefixe, entree.name)],
  )
}

describe("fichiers des guides vidéo (public/guides)", () => {
  it("attend trois fichiers par guide et par langue", () => {
    // 5 guides × 2 langues × (webm, vtt, jpg) aujourd'hui : un guide ou
    // une langue de plus agrandit la liste d'office.
    expect(ATTENDUS).toHaveLength(GUIDES.length * LANGUES_DES_GUIDES.length * 3)
  })

  it.each(ATTENDUS)("%s existe, n'est pas vide et a la signature de son type", (relatif) => {
    const chemin = join(DOSSIER, relatif)
    const present = fichiersPresents().includes(relatif)
    expect(present, `${relatif} manque dans public/guides : tournez le guide (README, « Guides vidéo »)`).toBe(true)
    const contenu = readFileSync(chemin)
    expect(contenu.length, `${relatif} est vide`).toBeGreaterThan(0)
    const extension = relatif.split(".").pop() as keyof typeof SIGNATURES
    expect(SIGNATURES[extension](contenu), `${relatif} n'a pas la signature d'un .${extension}`).toBe(true)
  })

  it("ne contient aucun fichier qu'aucun guide du catalogue ne sert", () => {
    // Un guide retiré de `guides.ts`, ou un fichier mal nommé, partirait
    // dans l'image sans que personne ne puisse le voir.
    const orphelins = fichiersPresents().filter((relatif) => !ATTENDUS.includes(relatif))
    expect(orphelins, "fichiers orphelins dans public/guides").toEqual([])
  })

  it(`pèse au plus ${BUDGET_EN_OCTETS} octets`, () => {
    // Un dépassement se décide (débit de réencodage, nombre de guides),
    // il ne s'absorbe pas en relevant ce chiffre sans le consigner dans la
    // décision 118.
    const poids = fichiersPresents().reduce((total, relatif) => total + statSync(join(DOSSIER, relatif)).size, 0)
    expect(poids, `public/guides pèse ${poids} octets`).toBeLessThanOrEqual(BUDGET_EN_OCTETS)
  })
})
