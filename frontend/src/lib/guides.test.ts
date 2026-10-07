import { readFileSync } from "node:fs"
import { join } from "node:path"
import { describe, expect, it } from "vitest"
import en from "@/i18n/en.json"
import fr from "@/i18n/fr.json"
import { LANGUAGES } from "@/i18n"
import {
  GUIDES,
  LANGUES_DES_GUIDES,
  fichierDuGuide,
  guidesVisibles,
  langueDeGuide,
  type IdDeGuide,
  type LangueDeGuide,
} from "./guides"

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
    expect(langueDeGuide("de")).toBe("fr")
    expect(langueDeGuide("")).toBe("fr")
    expect(fichierDuGuide("ouvrir-un-projet", "en", "vtt")).toBe("/guides/en/ouvrir-un-projet.vtt")
  })

  it("filme exactement les langues de l'interface", () => {
    // `guides.ts` ne dépend de rien (le script de tournage le lit sous
    // Node) : il ne peut pas importer `LANGUAGES`. Ce test garde l'égalité,
    // pour qu'une langue de l'interface ne reste pas sans guide, ni une
    // langue filmée sans interface.
    expect([...LANGUES_DES_GUIDES]).toEqual([...LANGUAGES])
  })

  it("sert chaque langue filmée à qui la parle, avec ou sans région", () => {
    // `langueDeGuide` lit la liste au lieu d'un « en » en dur : une
    // troisième langue tournée serait aussi servie.
    for (const langue of LANGUES_DES_GUIDES) {
      expect(langueDeGuide(langue), langue).toBe(langue)
      expect(langueDeGuide(`${langue}-XX`), langue).toBe(langue)
    }
  })

  it("n'adresse que des guides du catalogue", () => {
    // Vérifié par `tsc -b` : sans le typage `IdDeGuide`, la directive
    // ci-dessous deviendrait inutile et la compilation échouerait.
    // @ts-expect-error — « inconnu » n'est pas un IdDeGuide.
    expect(fichierDuGuide("inconnu", "fr", "webm")).toBe("/guides/fr/inconnu.webm")
  })
})

/**
 * Le texte des guides, tel que le manager le lit (relu au contrôle de la
 * 2.1.0). Les sous-titres naissent des `LEGENDES` du script de tournage,
 * qui s'exécute à l'import : on les lit donc dans sa source, comme le
 * catalogue lit le disque. Un sous-titre est une chaîne sur une ligne ; une
 * mise en forme qui changerait cela fait échouer ce test, pas le tournage.
 */
describe("texte des guides vidéo", () => {
  const SCRIPT = readFileSync(join(process.cwd(), "scripts", "tourner-guides.mts"), "utf8")

  /** Le bloc d'une constante du script, de sa déclaration à l'accolade qui la ferme. */
  function bloc(nom: string) {
    const debut = SCRIPT.indexOf(`const ${nom}`)
    expect(debut, nom).toBeGreaterThanOrEqual(0)
    return SCRIPT.slice(debut, SCRIPT.indexOf("\n}\n", debut))
  }

  /** La partie d'un bloc qui concerne un guide : de sa clé à la clé du guide suivant. */
  function partie(texte: string, id: string) {
    const debut = texte.indexOf(`"${id}": {`)
    expect(debut, id).toBeGreaterThanOrEqual(0)
    const suite = texte.slice(debut + id.length + 4).search(/\n {2}"[a-z-]+": \{/)
    return suite < 0 ? texte.slice(debut) : texte.slice(debut, debut + id.length + 4 + suite)
  }

  /** Les sous-titres d'un guide dans une langue, interpolations remplacées par « … ». */
  function legendes(id: IdDeGuide, langue: LangueDeGuide) {
    const corps = partie(bloc("LEGENDES"), id).match(new RegExp(`\\n {4}${langue}: \\(t\\) => \\[\\n([\\s\\S]*?)\\n {4}\\],`))
    expect(corps, `${id}/${langue}`).not.toBeNull()
    return corps![1]
      .split("\n")
      .filter((ligne) => /^ {6}["`]/.test(ligne))
      .map((ligne) => ligne.trim().replace(/,$/, "").slice(1, -1).replace(/\$\{[^}]*\}/g, "…"))
  }

  const tous = (langue: LangueDeGuide) => GUIDES.flatMap((guide) => legendes(guide.id, langue))

  /** Les textes d'une branche du dictionnaire, sans ses clés (« soumettre-un-dossier » est un identifiant). */
  function textes(branche: unknown): string[] {
    if (typeof branche === "string") return [branche]
    return Object.values(branche as Record<string, unknown>).flatMap(textes)
  }

  it("donne à chaque guide autant de sous-titres que son tournage en dit", () => {
    const tournages = bloc("TOURNAGES")
    for (const guide of GUIDES) {
      const dits = [...partie(tournages, guide.id).matchAll(/\bs\.dire\((\d+)\)/g)].map((appel) => Number(appel[1]))
      const attendus = [...new Set(dits)].sort((a, b) => a - b)
      for (const langue of LANGUES_DES_GUIDES) {
        const nombre = legendes(guide.id, langue).length
        expect(nombre, `${guide.id}/${langue}`).toBeGreaterThan(0)
        expect(attendus, `${guide.id}/${langue}`).toEqual([...Array(nombre).keys()])
      }
    }
  })

  it("dit en anglais « dossier », jamais « file » pour un dossier", () => {
    // Décision de la 2.2 : « file » désignait aussi le champ « File » du
    // classeur sur l'écran filmé. Le dossier garde son nom en anglais.
    for (const texte of textes(en.guides)) expect(texte).not.toMatch(/\bfiles?\b/i)
    // Seul « Choose the file » parle d'un fichier : la pièce à déposer.
    for (const legende of tous("en")) expect(legende.replace("Choose the file", "")).not.toMatch(/\bfiles?\b/i)
  })

  it("tient chaque sous-titre en deux lignes du lecteur : 84 caractères au plus", () => {
    // Un libellé interpolé compte pour « … » : la marge couvre les plus longs.
    for (const langue of LANGUES_DES_GUIDES) {
      for (const legende of tous(langue)) expect(legende.length, legende).toBeLessThanOrEqual(84)
    }
  })

  it("dit que soumettre est immédiat et sans retour, et ce que valent les pièces manquantes", () => {
    const francais = legendes("soumettre-un-dossier", "fr").join(" ")
    expect(francais).toMatch(/sans confirmation ni retour/)
    expect(francais).toMatch(/seul le siège peut le rouvrir/)
    expect(francais).toMatch(/brouillon d'un collègue/)
    expect(francais).toMatch(/avertissement/)
    const anglais = legendes("soumettre-un-dossier", "en").join(" ")
    expect(anglais).toMatch(/no confirmation and no way back/)
    expect(anglais).toMatch(/only headquarters can reopen/)
    expect(anglais).toMatch(/colleague's draft/)
    expect(anglais).toMatch(/warning/)
  })

  it("écrit « financial support » sans article", () => {
    for (const texte of textes(en.guides)) expect(texte).not.toContain("a financial support")
    for (const legende of tous("en")) expect(legende).not.toContain("a financial support")
  })

  it("ne promet pas en tête de page plus que les guides ne couvrent", () => {
    expect(fr.guides.description).not.toMatch(/chaque geste/i)
    expect(fr.guides.description).toMatch(/déclaration/)
    expect(en.guides.description).not.toMatch(/every step/i)
    expect(en.guides.description).toMatch(/declare/)
  })

  it("dit qui ajoute des lignes, ce que la soumission exige et la conversion", () => {
    const francais = legendes("saisir-une-ligne", "fr").join(" ")
    expect(francais).toMatch(/vous seul/)
    expect(francais).toMatch(/[ÉéEe]quipe et manager responsable sont exigés/)
    expect(francais).toMatch(/autre devise/)
    const anglais = legendes("saisir-une-ligne", "en").join(" ")
    expect(anglais).toMatch(/only you/)
    expect(anglais).toMatch(/team and a responsible manager are required/)
    expect(anglais).toMatch(/another currency/)
  })

  it("montre les colonnes du classeur et finit sur la soumission", () => {
    // Les colonnes viennent du module qui écrit le classeur filmé, lui-même
    // aligné sur `COLONNES_OBLIGATOIRES` de `backend/reporting/imports.py`.
    const source = readFileSync(join(process.cwd(), "scripts", "guides", "classeur.ts"), "utf8")
    const colonnes = [...source.match(/COLONNES_DU_CLASSEUR = \[([^\]]*)\]/)![1].matchAll(/"([^"]+)"/g)].map((c) => c[1])
    expect(colonnes.length).toBeGreaterThan(0)
    for (const [langue, soumettre] of [["fr", /soumettez ensuite le dossier/], ["en", /then submit the dossier/]] as const) {
      const sousTitres = legendes("importer-un-classeur", langue)
      expect(sousTitres.some((s) => colonnes.every((colonne) => s.includes(colonne))), langue).toBe(true)
      expect(sousTitres.at(-1), langue).toMatch(soumettre)
    }
  })

  it("rédige une condition comme une condition", () => {
    for (const langue of LANGUES_DES_GUIDES) {
      for (const legende of tous(langue)) expect(legende).not.toMatch(/^(Tout est correct|Everything is correct)/)
    }
  })
})
