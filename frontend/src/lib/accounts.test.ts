import { describe, expect, it } from "vitest"
import { platformClosed, totpEnrolmentRequired } from "@/lib/accounts"
import type { Me } from "@/lib/types"
import { PERMISSIONS_DU_PAYS } from "@/test/permissions-fixtures"

function profil(overrides: Partial<Me>): Me {
  return {
    id: 1,
    username: "togo.innov",
    first_name: "",
    last_name: "",
    email: "",
    role: "manager",
    role_display: "Manager (pays)",
    countries: [],
    teams: [],
    has_global_scope: false,
    must_change_password: false,
    totp_required: false,
    totp_confirmed: true,
    language: "fr",
    supervision: false,
    permissions: {
      ...PERMISSIONS_DU_PAYS,
    },
    workflow: { require_review_step: false },
    ...overrides,
  }
}

describe("totpEnrolmentRequired", () => {
  it("n'impose rien par défaut : la double authentification se propose", () => {
    expect(totpEnrolmentRequired(profil({ totp_confirmed: false }))).toBe(false)
    expect(totpEnrolmentRequired(profil({ totp_required: false, totp_confirmed: false }))).toBe(false)
  })

  it("impose l'enrôlement quand le serveur le dit et que le compte ne l'a pas fait", () => {
    expect(totpEnrolmentRequired(profil({ totp_required: true, totp_confirmed: false }))).toBe(true)
  })

  it("laisse tranquille un compte enrôlé, même sous politique stricte", () => {
    expect(totpEnrolmentRequired(profil({ totp_required: true, totp_confirmed: true }))).toBe(false)
  })

  it("ne dit rien sans profil ni sur un serveur qui ignore la 2FA", () => {
    expect(totpEnrolmentRequired(null)).toBe(false)
    expect(totpEnrolmentRequired(profil({ totp_required: true }))).toBe(false)
  })
})

describe("platformClosed", () => {
  it("ferme sur un mot de passe provisoire", () => {
    expect(platformClosed(profil({ must_change_password: true }))).toBe(true)
  })

  it("ferme sur une 2FA imposée et non enrôlée, pas sur une 2FA seulement proposée", () => {
    expect(platformClosed(profil({ totp_required: true, totp_confirmed: false }))).toBe(true)
    expect(platformClosed(profil({ totp_confirmed: false }))).toBe(false)
  })

  it("reste ouverte à un compte en règle", () => {
    expect(platformClosed(profil({ totp_confirmed: true }))).toBe(false)
    expect(platformClosed(null)).toBe(false)
  })
})
