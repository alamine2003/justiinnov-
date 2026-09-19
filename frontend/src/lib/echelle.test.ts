/**
 * L'échelle décide de ce qui tient dans le cadre : mesurée sur le seul
 * montant attribué, le segment de dépassement en sortait.
 */
import { describe, expect, it } from "vitest"
import { echelleCommune } from "@/lib/echelle"

describe("echelleCommune", () => {
  const ligne = (allocated: string, consumed: string, engaged: string) => ({
    allocated,
    consumed,
    engaged,
  })

  it("retient la plus grande enveloppe attribuée", () => {
    expect(
      echelleCommune([ligne("100", "10", "0"), ligne("450", "20", "0"), ligne("300", "0", "0")]),
    ).toBe(450)
  })

  it("compte l'engagé avec le consommé, pour que le dépassement tienne dans le cadre", () => {
    // Enveloppe de 100, consommé 80, engagé 60 : la barre va jusqu'à 140.
    // Une échelle qui ne regarderait que l'attribué s'arrêterait à 100 et le
    // segment corail sortirait du cadre.
    expect(echelleCommune([ligne("100", "80", "60")])).toBe(140)
  })

  it("ne descend jamais à zéro, même sans ligne ni enveloppe", () => {
    expect(echelleCommune([])).toBe(1)
    expect(echelleCommune([ligne("0", "0", "0")])).toBe(1)
  })
})
