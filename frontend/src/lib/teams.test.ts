import { describe, expect, it } from "vitest"
import { scopedTeams, teamRequired } from "@/lib/teams"
import type { Me } from "@/lib/types"

const EQUIPES = [
  { id: 1, name: "Commerciale" },
  { id: 2, name: "Marketing" },
  { id: 3, name: "Logistique" },
]

// `undefined` : un serveur qui ne connaîtrait pas encore les équipes.
function profil(teams: Me["teams"] | undefined): Me {
  return { teams } as unknown as Me
}

describe("scopedTeams", () => {
  it("laisse la liste entière sans profil", () => {
    expect(scopedTeams(EQUIPES, null)).toEqual(EQUIPES)
  })

  it("laisse la liste entière à un rôle sans équipe de périmètre", () => {
    expect(scopedTeams(EQUIPES, profil([]))).toEqual(EQUIPES)
    expect(scopedTeams(EQUIPES, profil(undefined))).toEqual(EQUIPES)
  })

  it("ne garde que les équipes du manager", () => {
    const me = profil([
      { id: 2, name: "Marketing", country: 1 },
      { id: 9, name: "Ailleurs", country: 2 },
    ])

    expect(scopedTeams(EQUIPES, me)).toEqual([{ id: 2, name: "Marketing" }])
  })
})

describe("teamRequired", () => {
  it("exige une équipe d'un manager rattaché à des équipes", () => {
    // Le serveur répond 400 « Choisissez une de vos équipes. » sinon.
    expect(teamRequired(profil([{ id: 2, name: "Marketing", country: 1 }]))).toBe(true)
  })

  it("n'exige rien des autres", () => {
    expect(teamRequired(null)).toBe(false)
    expect(teamRequired(profil([]))).toBe(false)
    expect(teamRequired(profil(undefined))).toBe(false)
  })
})
