import { describe, expect, it } from "vitest"
import { echelleCommune, echelleDe, mesuresEnXof } from "@/lib/echelle"

/** Une ligne de pays, réduite à ce que l'échelle en lit. */
function ligne(
  allocated: string,
  consumed: string,
  engaged: string,
  xof?: [string, string, string],
) {
  return {
    allocated,
    consumed,
    engaged,
    allocated_xof: xof?.[0] ?? null,
    consumed_xof: xof?.[1] ?? null,
    engaged_xof: xof?.[2] ?? null,
  }
}

describe("échelle commune des barres de pays", () => {
  it("dessine avec les montants en FCFA, pas avec ceux de la devise locale", () => {
    // Une enveloppe guinéenne de 10 000 000 GNF vaut 1 000 000 FCFA :
    // moins que celle du Togo, alors que son nombre est dix fois plus gros.
    const mesures = mesuresEnXof([
      ligne("2000000", "1000000", "0", ["2000000", "1000000", "0"]),
      ligne("10000000", "5000000", "0", ["1000000", "500000", "0"]),
    ])
    const commune = echelleCommune(mesures)

    expect(commune).toBe(2000000)
    expect(mesures[1].allocated).toBe(1000000)
    // Sans conversion, la Guinée aurait imposé l'échelle et écrasé le Togo.
    expect(echelleDe(mesures[1], commune)).toBe(2000000)
  })

  it("replie sur ses propres montants la ligne dont la devise n'a pas de taux", () => {
    const mesures = mesuresEnXof([
      ligne("2000000", "1000000", "0", ["2000000", "1000000", "0"]),
      ligne("900000", "450000", "0"),
    ])
    const commune = echelleCommune(mesures)

    expect(commune).toBe(2000000)
    expect(mesures[1].converti).toBe(false)
    expect(mesures[1].allocated).toBe(900000)
    // Contre sa propre enveloppe : la proportion reste lisible.
    expect(echelleDe(mesures[1], commune)).toBe(900000)
  })

  it("ne laisse pas un champ absent vider toutes les barres", () => {
    // Une réponse d'un serveur plus ancien n'a pas les champs : `undefined`
    // n'est pas `null`, et un `Number(undefined)` aurait donné `NaN` —
    // l'échelle serait devenue `NaN` et chaque barre se serait vidée.
    const { allocated_xof: _a, consumed_xof: _c, engaged_xof: _e, ...ancienne } =
      ligne("800000", "400000", "0")
    const mesures = mesuresEnXof([ancienne])

    expect(mesures[0].converti).toBe(false)
    expect(mesures[0].allocated).toBe(800000)
    expect(Number.isFinite(echelleCommune(mesures))).toBe(true)
  })
})
