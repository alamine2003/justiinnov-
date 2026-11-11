import { describe, expect, it } from "vitest"
import {
  chargeDuCompte,
  perimetreDuRole,
  platformClosed,
  totpEnrolmentRequired,
  type RoleDeLaMatrice,
  type SaisieDuCompte,
} from "@/lib/accounts"
import type { AccountUser, Me } from "@/lib/types"
import { PERMISSIONS_DU_PAYS } from "@/test/permissions-fixtures"

// Une valeur sans rien d'un secret : un scanner de secrets lisait un vrai
// mot de passe dans une chaîne d'exemple.
const PROVISOIRE = "x".repeat(12)

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
    bi_url: null,
    api_version: null,
    alert_thresholds: [],
    permissions: {
      ...PERMISSIONS_DU_PAYS,
    },
    workflow: { require_review_step: false, suppressions_ouvertes: false },
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

// Les rôles tels que la matrice du serveur les décrit : c'est leur
// description (siège, toujours global), pas leur code, qui décide.
const ROLE_DU_PAYS: RoleDeLaMatrice = {
  value: "manager",
  label: "Manager",
  siege: false,
  always_global: false,
  assignable: true,
}
const ROLE_DU_SIEGE: RoleDeLaMatrice = {
  value: "admin",
  label: "Administrateur",
  siege: true,
  always_global: true,
  assignable: true,
}

function saisie(overrides: Partial<SaisieDuCompte> = {}): SaisieDuCompte {
  return {
    username: "togo.innov",
    firstName: "Ama",
    lastName: "Togo",
    email: "ama.togo@innovpharma.net",
    role: "manager",
    active: true,
    countryIds: [1],
    countriesTouched: false,
    teamIds: [],
    teamsTouched: false,
    password: "",
    ...overrides,
  }
}

function compte(overrides: Partial<AccountUser> = {}): AccountUser {
  return {
    id: 7,
    username: "togo.innov",
    first_name: "Ama",
    last_name: "Togo",
    email: "ama.togo@innovpharma.net",
    is_active: true,
    role: "manager",
    countries: [1],
    teams: [],
    ...overrides,
  } as AccountUser
}

describe("perimetreDuRole", () => {
  it("ne dit rien tant que la matrice n'est pas chargée", () => {
    expect(perimetreDuRole(undefined)).toEqual({
      isHeadquarters: false,
      alwaysGlobal: false,
      teamsApply: false,
    })
  })

  it("donne des équipes au pays, aucune au siège", () => {
    expect(perimetreDuRole(ROLE_DU_PAYS)).toEqual({
      isHeadquarters: false,
      alwaysGlobal: false,
      teamsApply: true,
    })
    expect(perimetreDuRole(ROLE_DU_SIEGE)).toEqual({
      isHeadquarters: true,
      alwaysGlobal: true,
      teamsApply: false,
    })
  })
})

describe("chargeDuCompte", () => {
  it("envoie tout à la création, identifiant et mot de passe compris", () => {
    const charge = chargeDuCompte(
      null,
      saisie({ password: PROVISOIRE, teamIds: [4] }),
      ROLE_DU_PAYS,
    )
    expect(charge).toEqual({
      first_name: "Ama",
      last_name: "Togo",
      email: "ama.togo@innovpharma.net",
      role: "manager",
      is_active: true,
      username: "togo.innov",
      countries: [1],
      teams: [4],
      password: PROVISOIRE,
    })
    // L'ordre des clés est celui qu'envoyait le formulaire.
    expect(Object.keys(charge)).toEqual([
      "first_name", "last_name", "email", "role", "is_active",
      "username", "countries", "teams", "password",
    ])
  })

  it("ne renvoie ni l'identifiant, ni le périmètre intact, ni un mot de passe vide", () => {
    expect(chargeDuCompte(compte(), saisie({ username: "autre" }), ROLE_DU_PAYS)).toEqual({
      first_name: "Ama",
      last_name: "Togo",
      email: "ama.togo@innovpharma.net",
      role: "manager",
      is_active: true,
    })
  })

  it("renvoie le périmètre et les équipes dès qu'on a coché", () => {
    expect(
      chargeDuCompte(compte(), saisie({ countryIds: [1, 2], countriesTouched: true }), ROLE_DU_PAYS),
    ).toMatchObject({ countries: [1, 2], teams: [] })
    const equipes = chargeDuCompte(compte(), saisie({ teamIds: [4], teamsTouched: true }), ROLE_DU_PAYS)
    expect(equipes.teams).toEqual([4])
    expect(equipes).not.toHaveProperty("countries")
  })

  it("renvoie le périmètre affiché quand le rôle change, pour que le serveur le revalide", () => {
    const charge = chargeDuCompte(
      compte({ role: "admin", countries: [] }),
      saisie({ role: "manager" }),
      ROLE_DU_PAYS,
    )
    expect(charge).toMatchObject({ role: "manager", countries: [1], teams: [] })
  })

  it("vide le périmètre et les équipes d'un rôle toujours global", () => {
    expect(
      chargeDuCompte(compte({ teams: [4] }), saisie({ role: "admin" }), ROLE_DU_SIEGE),
    ).toMatchObject({ countries: [], teams: [] })
    const creation = chargeDuCompte(null, saisie({ role: "admin" }), ROLE_DU_SIEGE)
    expect(creation.countries).toEqual([])
    expect(creation).not.toHaveProperty("teams")
  })

  it("ne renvoie rien du périmètre d'un compte global qui n'en a pas", () => {
    const charge = chargeDuCompte(
      compte({ role: "admin", countries: [], teams: [] }),
      saisie({ role: "admin", countryIds: [] }),
      ROLE_DU_SIEGE,
    )
    expect(charge).not.toHaveProperty("countries")
    expect(charge).not.toHaveProperty("teams")
  })

  it("laisse trancher le serveur tant que la matrice n'est pas chargée", () => {
    const charge = chargeDuCompte(null, saisie({ teamIds: [4] }), undefined)
    expect(charge.countries).toEqual([1])
    expect(charge).not.toHaveProperty("teams")
  })
})
