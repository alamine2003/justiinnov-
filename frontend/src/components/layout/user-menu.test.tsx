import { fireEvent, render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { UserMenu } from "./user-menu"
import type { Me } from "@/lib/types"

let me: Partial<Me> = {}
let droits = new Set<string>()
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({ me, can: (cle: string) => droits.has(cle) }),
}))
vi.mock("@/lib/install-prompt", () => ({ useInstallPrompt: () => ({ available: false, install: vi.fn() }) }))

function ouvrir() {
  render(
    <MemoryRouter>
      <UserMenu onLogout={vi.fn()} />
    </MemoryRouter>,
  )
  fireEvent.click(screen.getByRole("button", { name: "Menu du compte" }))
}

beforeEach(() => {
  me = { username: "do.innov", role_display: "Super administrateur", totp_confirmed: true, supervision: true, bi_url: null }
  droits = new Set()
})

/** Le BI de pilotage (décision 122) : le lien n'existe que si le serveur en donne l'adresse. */
describe("UserMenu — BI de pilotage", () => {
  it("ouvre l'adresse donnée par le serveur, dans un nouvel onglet", async () => {
    me = { ...me, bi_url: "https://bi.exemple.org/d/bi-vue-ensemble" }

    ouvrir()

    const lien = await screen.findByRole("menuitem", { name: "BI de pilotage" })
    expect(lien).toHaveAttribute("href", "https://bi.exemple.org/d/bi-vue-ensemble")
    expect(lien).toHaveAttribute("target", "_blank")
    expect(lien).toHaveAttribute("rel", "noopener noreferrer")
  })

  it("se tait sans adresse : pas de Grafana, ou pas la capacité", async () => {
    droits = new Set(["configuration.manage"])

    ouvrir()

    expect(await screen.findByRole("menuitem", { name: "Supervision" })).toBeInTheDocument()
    expect(screen.queryByRole("menuitem", { name: "BI de pilotage" })).toBeNull()
  })
})
