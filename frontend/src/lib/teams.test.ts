import { describe, expect, it } from "vitest"
import { scopedTeams } from "@/lib/teams"
import type { Me } from "@/lib/types"

const EQUIPES = [
  { id: 1, name: "Commerciale" },
  { id: 2, name: "Marketing" },
  { id: 3, name: "Logistique" },
]

function profil(teams: Me["teams"]): Me {
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
