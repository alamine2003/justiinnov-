import { readFileSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"

import {
  COLONNES_DU_CLASSEUR,
  classeur,
  classeurDuGuide,
  dateDeSaisie,
  dateDuClasseur,
  jourDuTournage,
  verifierLImport,
} from "./classeur.ts"

/** Relit une entrée d'une archive ZIP aux entrées stockées, comme `classeur` l'écrit. */
function entree(archive: Buffer, nom: string): string {
  let position = 0
  while (archive.readUInt32LE(position) === 0x04034b50) {
    const taille = archive.readUInt32LE(position + 18)
    const longueurDuNom = archive.readUInt16LE(position + 26)
    const longueurExtra = archive.readUInt16LE(position + 28)
    const debut = position + 30 + longueurDuNom + longueurExtra
    if (archive.toString("utf8", position + 30, position + 30 + longueurDuNom) === nom) {
      return archive.toString("utf8", debut, debut + taille)
    }
    position = debut + taille
  }
  throw new Error(`Entrée absente : ${nom}`)
}

/** Les cellules texte de la colonne B (DATE), hors en-tête. */
function datesDuClasseur(archive: Buffer) {
  const xml = entree(archive, "xl/worksheets/sheet1.xml")
  return [...xml.matchAll(/<c r="B(\d+)" t="inlineStr"><is><t>([^<]*)<\/t>/g)]
    .filter(([, ligne]) => ligne !== "1")
    .map(([, , valeur]) => valeur)
}

const JJ_MM_AAAA = /^\d{2}\/\d{2}\/\d{4}$/

describe("dates du tournage", () => {
  it("compte les jours à rebours, à travers les mois", () => {
    expect(dateDeSaisie(jourDuTournage(new Date(2026, 9, 6), 3))).toBe("2026-10-03T10:30")
    expect(dateDeSaisie(jourDuTournage(new Date(2028, 2, 2), 3))).toBe("2028-02-28T10:30")
  })

  // seed_demo n'ouvre que les enveloppes de l'année en cours ; une
  // date de l'année précédente ne trouverait aucune enveloppe.
  it("ne quitte jamais l'année du tournage", () => {
    const jour = jourDuTournage(new Date(2027, 0, 2), 15)
    expect(jour.getFullYear()).toBe(2027)
    expect(dateDuClasseur(jour)).toBe("01/01/2027")
  })

  it("écrit jour et mois sur deux chiffres", () => {
    expect(dateDuClasseur(new Date(2027, 0, 5))).toBe("05/01/2027")
    expect(dateDuClasseur(new Date(2026, 10, 30))).toBe("30/11/2026")
    expect(dateDeSaisie(new Date(2027, 0, 5), "08:15")).toBe("2027-01-05T08:15")
  })
})

describe("classeurDuGuide", () => {
  const options = { equipe: "Équipe Kara", responsable: "Kodjo Mensah" }
  const douze = Array.from({ length: 12 }, (_, i) => `Ligne ${i + 1}`)

  // `0${i + 1}/10/2026` donnait « 010/10/2026 » à la dixième
  // ligne, que le serveur refuse (« Date illisible »).
  it("date chaque ligne au format JJ/MM/AAAA, même au-delà de la neuvième", () => {
    const dates = datesDuClasseur(classeurDuGuide(douze, { ...options, aujourdhui: new Date(2026, 9, 6) }))
    expect(dates).toHaveLength(12)
    for (const date of dates) expect(date).toMatch(JJ_MM_AAAA)
    expect(dates[0]).toBe("02/10/2026")
    expect(dates[9]).toBe("23/09/2026")
  })

  // Les lignes précèdent la ligne saisie à la main (trois jours
  // avant le tournage) et restent dans l'année du tournage.
  it("date les lignes des jours qui précèdent, dans l'année du tournage", () => {
    for (const aujourdhui of [new Date(2031, 6, 14), new Date(2031, 0, 3)]) {
      const saisie = jourDuTournage(aujourdhui, 3)
      const dates = datesDuClasseur(classeurDuGuide(douze, { ...options, aujourdhui }))
      for (const date of dates) {
        const [jour, mois, annee] = date.split("/").map(Number)
        const valeur = new Date(annee, mois - 1, jour)
        expect(annee).toBe(2031)
        expect(valeur <= saisie).toBe(true)
      }
    }
  })

  it("porte l'en-tête historique, l'équipe et le responsable choisis", () => {
    const xml = entree(classeurDuGuide(["Location du stand"], { ...options, aujourdhui: new Date(2026, 9, 6) }), "xl/worksheets/sheet1.xml")
    for (const colonne of COLONNES_DU_CLASSEUR) expect(xml).toContain(`<t>${colonne}</t>`)
    expect(xml).toContain("<t>Équipe Kara</t>")
    expect(xml).toContain("<t>Kodjo Mensah</t>")
  })

  it("échappe le texte des cellules", () => {
    const xml = entree(classeur([["A & <B>"]]), "xl/worksheets/sheet1.xml")
    expect(xml).toContain("<t>A &amp; &lt;B&gt;</t>")
  })
})

describe("verifierLImport", () => {
  const attendu = { lignes: 3, simulation: true }

  it("laisse passer un import qui a fait ce que le guide montre", () => {
    expect(() => verifierLImport("Simulation", 200, { lignes_creees: 3, erreurs: [], dry_run: true }, attendu)).not.toThrow()
    expect(() =>
      verifierLImport("Import", 200, { lignes_creees: 3, erreurs: [], dry_run: false }, { lignes: 3, simulation: false }),
    ).not.toThrow()
  })

  // La réponse réelle du serveur quand le dossier « Stands » porte une autre
  // équipe que celle du classeur : 200, aucune ligne, des erreurs. L'écran
  // affichait le même titre de résultat que pour un import réussi.
  it("lève sur un classeur refusé malgré le statut 200", () => {
    const refuse = {
      lignes_creees: 0,
      equipes_creees: 0,
      managers_crees: 0,
      dry_run: true,
      erreurs: [{ ligne: 2, motif: "Le dossier « TG-P-2026-004-D002 » porte l'équipe « Équipe Lomé » : la ligne doit porter la même." }],
    }
    expect(() => verifierLImport("Simulation", 200, refuse, attendu)).toThrow(/1 erreur\(s\).*Équipe Lomé/)
    expect(() => verifierLImport("Simulation", 200, refuse, attendu)).toThrow(/lignes_creees vaut 0, 3 attendue/)
  })

  it("lève quand le nombre de lignes diffère, sans erreur déclarée", () => {
    expect(() => verifierLImport("Import", 200, { lignes_creees: 2, erreurs: [], dry_run: false }, { lignes: 3, simulation: false })).toThrow(
      /lignes_creees vaut 2/,
    )
  })

  it("lève sur un statut d'échec, une réponse sans erreurs ou une simulation prise pour un import", () => {
    expect(() => verifierLImport("Import", 400, { lignes_creees: 3, erreurs: [], dry_run: true }, attendu)).toThrow(/statut HTTP 400/)
    expect(() => verifierLImport("Import", 200, {}, attendu)).toThrow(/sans liste « erreurs »/)
    expect(() => verifierLImport("Import", 200, { lignes_creees: 3, erreurs: [], dry_run: true }, { lignes: 3, simulation: false })).toThrow(
      /dry_run vaut true/,
    )
  })
})

describe("le script de tournage", () => {
  const source = readFileSync(path.resolve(import.meta.dirname, "../tourner-guides.mts"), "utf8")

  it("n'écrit aucune année en dur : les dates suivent le jour du tournage", () => {
    expect(source).not.toMatch(/\b20[2-9]\d\b/)
  })

  it("ne choisit aucune option par position", () => {
    expect(source).not.toMatch(/\{\s*index:\s*\d+\s*\}/)
  })

  it("vérifie la réponse de l'API à la simulation et à l'import", () => {
    expect(source.match(/importerEtVerifier\(/g)?.length ?? 0).toBeGreaterThanOrEqual(3)
    expect(source).toContain("waitForResponse")
  })
})
