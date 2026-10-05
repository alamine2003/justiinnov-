import { describe, expect, it } from "vitest"
import en from "@/i18n/en.json"
import fr from "@/i18n/fr.json"
import { GUIDES, fichierDuGuide, guidesVisibles, langueDeGuide } from "./guides"

describe("catalogue des guides vidéo", () => {
  it("donne à chaque guide un titre et une description, en français et en anglais", () => {
    for (const dictionnaire of [fr, en]) {
      for (const guide of GUIDES) {
        const entree = dictionnaire.guides.liste[guide.id]
        expect(entree?.titre, guide.id).toBeTruthy()
        expect(entree?.description, guide.id).toBeTruthy()
      }
    }
    expect(new Set(GUIDES.map((guide) => guide.id)).size).toBe(GUIDES.length)
  })

  it("ne montre que les guides des capacités du compte, dans l'ordre", () => {
    const can = (capacite: string) => ["expenses.create", "dossiers.submit"].includes(capacite)
    expect(guidesVisibles(can).map((guide) => guide.id)).toEqual(["saisir-une-ligne", "soumettre-un-dossier"])
    expect(guidesVisibles(() => false)).toEqual([])
  })

  it("range les fichiers par langue, le français à défaut", () => {
    expect(langueDeGuide("en-GB")).toBe("en")
    expect(langueDeGuide("fr")).toBe("fr")
    expect(langueDeGuide(undefined)).toBe("fr")
    expect(fichierDuGuide("ouvrir-un-projet", "en", "vtt")).toBe("/guides/en/ouvrir-un-projet.vtt")
  })
})
