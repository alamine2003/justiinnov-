import { render, screen } from "@testing-library/react"
import { MemoryRouter } from "react-router-dom"
import { describe, expect, it } from "vitest"
import { Evenement } from "./evenement"
import type { EntreeHistorique } from "@/lib/types"

function entree(action: string): EntreeHistorique {
  return {
    source: "circuit", id: 1, action, action_display: action, objet: "Dossier",
    object_id: 20, label: "TG-P-2026-001-D001", user: "direction.demo", ip_address: null,
    motif: "", avant: null, apres: null, note: "", created_at: "2026-10-08T10:00:00Z",
  } as unknown as EntreeHistorique
}

function afficher(action: string) {
  return render(
    <MemoryRouter>
      <ul>
        <Evenement entree={entree(action)} />
      </ul>
    </MemoryRouter>,
  )
}

describe("Evenement", () => {
  it("mène à la fiche du dossier", () => {
    afficher("submitted")
    expect(screen.getByRole("link")).toHaveAttribute("href", "/dossiers/20")
  })

  it("ne mène nulle part pour un dossier mis à la corbeille (décision 120)", () => {
    afficher("trashed")
    expect(screen.queryByRole("link")).toBeNull()
  })
})
