import { describe, expect, it } from "vitest"

import { GUIDES } from "../../src/lib/guides.ts"
import {
  echecDuGeste,
  ffmpegInutilisable,
  guidesDuTournage,
  langueDuTournage,
  libelle,
  proposeLibvpx,
} from "./selection.ts"

const TOUS = GUIDES.map((guide) => guide.id)

describe("guidesDuTournage (GUIDES_SEULS)", () => {
  it("tourne tous les guides, dans l'ordre, quand la variable est absente", () => {
    expect(guidesDuTournage(undefined)).toEqual(TOUS)
  })

  // "" et "," donnaient [] et le tournage finissait en succès sans
  // rien avoir tourné.
  it.each(["", ",", " ", " , , "])("refuse une liste vide (%j)", (valeur) => {
    expect(() => guidesDuTournage(valeur)).toThrow("GUIDES_SEULS ne nomme aucun guide")
  })

  it("normalise les espaces autour des noms", () => {
    expect(guidesDuTournage(" soumettre-un-dossier , ouvrir-un-projet ")).toEqual([
      "ouvrir-un-projet",
      "soumettre-un-dossier",
    ])
  })

  it("garde l'ordre des guides et ignore un doublon", () => {
    expect(guidesDuTournage("joindre-une-piece,saisir-une-ligne,joindre-une-piece")).toEqual([
      "saisir-une-ligne",
      "joindre-une-piece",
    ])
  })

  it("arrête tout sur un nom inconnu, en le nommant", () => {
    expect(() => guidesDuTournage("saisir-une-ligne,inconnu")).toThrow("Guides inconnus : inconnu.")
  })
})

describe("langueDuTournage (GUIDES_LANGUE)", () => {
  it.each(["fr", "en", " en "])("accepte %j", (valeur) => {
    expect(langueDuTournage(valeur)).toBe(valeur.trim())
  })

  it.each([undefined, "", "de", "fr,en"])("refuse %j", (valeur) => {
    expect(() => langueDuTournage(valeur)).toThrow("GUIDES_LANGUE doit valoir fr ou en")
  })
})

describe("proposeLibvpx (ffmpeg -encoders)", () => {
  // Sortie réelle du ffmpeg livré avec Playwright (ffmpeg-1011).
  const PLAYWRIGHT = [
    "Encoders:",
    " V..... = Video",
    " ------",
    " VF...D png                  PNG (Portable Network Graphics) image",
    " V....D libvpx               libvpx VP8 (codec vp8)",
  ].join("\n")

  it("reconnaît l'encodeur VP8", () => {
    expect(proposeLibvpx(PLAYWRIGHT)).toBe(true)
  })

  it("ne se contente pas de VP9 ni d'une sortie vide", () => {
    expect(proposeLibvpx(" V....D libvpx-vp9           libvpx VP9 (codec vp9)")).toBe(false)
    expect(proposeLibvpx("")).toBe(false)
  })

  it("nomme GUIDES_FFMPEG dans le message d'arrêt", () => {
    expect(ffmpegInutilisable("/inexistant", true, "ENOENT").message).toMatch(
      /^GUIDES_FFMPEG désigne \/inexistant, .*ENOENT/,
    )
    expect(ffmpegInutilisable("/opt/ffmpeg", false, "libvpx absent").message).toContain("GUIDES_FFMPEG")
  })
})

describe("libelle (dictionnaire de l'interface)", () => {
  const BRUT = { commun: { creer: "Créer", bonjour: "Bonjour {{nom}}" }, plat: "texte" }

  it("lit une clé et interpole ses valeurs", () => {
    expect(libelle(BRUT, "fr", "commun.creer")).toBe("Créer")
    expect(libelle(BRUT, "fr", "commun.bonjour", { nom: "Kodjo" })).toBe("Bonjour Kodjo")
  })

  // Un segment intermédiaire absent levait un TypeError qui ne nommait pas la clé.
  it.each(["inexistant.cle", "commun.inexistant", "plat.sous", "commun"])("nomme la clé absente %j", (cle) => {
    expect(() => libelle(BRUT, "fr", cle)).toThrow(`Clé absente du dictionnaire fr : ${cle}`)
  })
})

describe("echecDuGeste", () => {
  // L'exception d'un `waitFor` masquait les erreurs de console.
  it("joint les erreurs de console au message du geste et garde la cause", () => {
    const cause = new Error("locator.waitFor: Timeout 30000ms exceeded.")
    const erreur = echecDuGeste("fr/soumettre-un-dossier", cause, [
      "Failed to load resource: the server responded with a status of 500",
    ])
    expect(erreur.message).toContain("fr/soumettre-un-dossier")
    expect(erreur.message).toContain("Timeout 30000ms exceeded")
    expect(erreur.message).toContain("status of 500")
    expect(erreur.cause).toBe(cause)
  })

  it("dit qu'il n'y en avait aucune", () => {
    expect(echecDuGeste("en/ouvrir-un-projet", "refus", []).message).toContain("Aucune erreur de console")
  })
})
