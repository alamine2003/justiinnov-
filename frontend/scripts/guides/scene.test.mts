/**
 * Les sous-titres livrés (`public/guides/<langue>/<guide>.vtt`) sont écrits
 * par `sousTitres()` et `horodatage()` au tournage : un horodatage mal formé
 * ou une réplique qui déborde ne se voit qu'au visionnage, langue par
 * langue. Ces tests en tiennent la forme.
 */
import { describe, expect, it } from "vitest"

import { espacesFines, horodatage, sousTitres } from "./scene.ts"

describe("horodatage (WebVTT, hh:mm:ss.mmm)", () => {
  it("écrit zéro sur toute sa largeur", () => {
    expect(horodatage(0)).toBe("00:00:00.000")
  })

  it("complète les millisecondes sur trois chiffres", () => {
    expect(horodatage(5)).toBe("00:00:00.005")
    expect(horodatage(35_979)).toBe("00:00:35.979")
  })

  it("arrondit à la milliseconde et ne descend pas sous zéro", () => {
    expect(horodatage(1_234.4)).toBe("00:00:01.234")
    expect(horodatage(1_234.6)).toBe("00:00:01.235")
    expect(horodatage(999.5)).toBe("00:00:01.000")
    expect(horodatage(-20)).toBe("00:00:00.000")
  })

  it("compte les minutes", () => {
    expect(horodatage(61_000)).toBe("00:01:01.000")
    expect(horodatage(59 * 60_000 + 59_999)).toBe("00:59:59.999")
  })

  it("compte les heures au-delà de la soixantième minute", () => {
    expect(horodatage(3_600_000)).toBe("01:00:00.000")
    expect(horodatage(3_600_005)).toBe("01:00:00.005")
    expect(horodatage(2 * 3_600_000 + 3 * 60_000 + 4_050)).toBe("02:03:04.050")
  })
})

describe("sousTitres (fichier WebVTT)", () => {
  const reperes = [
    { debut: 0, texte: "Ouvrez le projet." },
    { debut: 2_500, texte: "Choisissez le dossier." },
    { debut: 61_250, texte: "Soumettez." },
  ]

  it("écrit le fichier entier : en-tête, blocs numérotés, enchaînés jusqu'à la fin", () => {
    expect(sousTitres(reperes, 65_000)).toBe(
      "WEBVTT\n" +
        "\n" +
        "1\n" +
        "00:00:00.000 --> 00:00:02.500\n" +
        "Ouvrez le projet.\n" +
        "\n" +
        "2\n" +
        "00:00:02.500 --> 00:01:01.250\n" +
        "Choisissez le dossier.\n" +
        "\n" +
        "3\n" +
        "00:01:01.250 --> 00:01:05.000\n" +
        "Soumettez.\n",
    )
  })

  it("ouvre le fichier par « WEBVTT » suivi d'une ligne vide", () => {
    expect(sousTitres(reperes, 65_000).startsWith("WEBVTT\n\n1\n")).toBe(true)
  })

  it("numérote les blocs à partir de 1, dans l'ordre des repères", () => {
    const blocs = sousTitres(reperes, 65_000).split("\n\n").slice(1)
    expect(blocs.map((bloc) => bloc.split("\n")[0])).toEqual(["1", "2", "3"])
  })

  it("fait finir chaque réplique au début de la suivante, sans trou ni chevauchement", () => {
    const temps = [...sousTitres(reperes, 65_000).matchAll(/^(\S+) --> (\S+)$/gm)].map((m) => [m[1], m[2]])
    expect(temps).toHaveLength(3)
    for (let i = 0; i < temps.length - 1; i++) expect(temps[i][1]).toBe(temps[i + 1][0])
  })

  it("fait durer la dernière réplique jusqu'à la fin de la vidéo", () => {
    expect(sousTitres([{ debut: 1_000, texte: "Seule." }], 9_876)).toBe(
      "WEBVTT\n\n1\n00:00:01.000 --> 00:00:09.876\nSeule.\n",
    )
  })

  it("se réduit à l'en-tête sans repère", () => {
    expect(sousTitres([], 5_000)).toBe("WEBVTT\n\n")
  })
})

describe("espacesFines (typographie française des sous-titres)", () => {
  const FINE = "\u202f"

  it("lie « : », « ; », « ? » et « ! » au mot qui précède", () => {
    expect(espacesFines("Choisissez son type : il fixe ; prêt ? oui !")).toBe(
      `Choisissez son type${FINE}: il fixe${FINE}; prêt${FINE}? oui${FINE}!`,
    )
  })

  it("garde les guillemets français collés à leur texte", () => {
    expect(espacesFines("Cliquez sur « Créer ».")).toBe(`Cliquez sur «${FINE}Créer${FINE}».`)
  })

  it("remplace une espace insécable ordinaire, ne double rien, ne touche pas une heure", () => {
    expect(espacesFines("type\u00a0: oui")).toBe(`type${FINE}: oui`)
    expect(espacesFines(espacesFines("type : oui"))).toBe(`type${FINE}: oui`)
    expect(espacesFines("à 10:30")).toBe("à 10:30")
  })
})
