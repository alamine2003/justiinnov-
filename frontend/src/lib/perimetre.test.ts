import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"
import en from "@/i18n/en.json"
import fr from "@/i18n/fr.json"
import { FILIALES } from "@/lib/perimetre"

/**
 * La page d'accueil recopie les codes des filiales, parce qu'elle s'affiche
 * sans session. La référence reste `backend/core/africa.py` : ce test relit
 * le fichier Python et refuse qu'une filiale manque d'un côté ou de l'autre,
 * ou qu'un nom français diffère de celui du serveur.
 */
function filialesDuServeur(): Record<string, string> {
  const source = readFileSync(
    resolve(import.meta.dirname, "../../../backend/core/africa.py"),
    "utf8",
  )
  const bloc = source.match(/AFRICAN_COUNTRIES = \{([\s\S]*?)\n\}/)
  if (!bloc) throw new Error("AFRICAN_COUNTRIES introuvable dans africa.py")
  return Object.fromEntries(
    [...bloc[1].matchAll(/"([A-Z]{2})": "([^"]+)"/g)].map((m) => [m[1], m[2]]),
  )
}

describe("périmètre des filiales", () => {
  const serveur = filialesDuServeur()

  it("recopie exactement les codes de backend/core/africa.py", () => {
    expect([...FILIALES].sort()).toEqual(Object.keys(serveur).sort())
    expect(FILIALES).toHaveLength(17)
  })

  it("nomme chaque filiale comme le serveur, en français, et la traduit en anglais", () => {
    for (const code of FILIALES) {
      expect(fr.filiales[code]).toBe(serveur[code])
      expect(en.filiales[code]).toBeTruthy()
    }
  })
})
