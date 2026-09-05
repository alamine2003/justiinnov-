import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ProofPanel } from "./proof-panel"
import type { Proof } from "@/lib/types"

// Le droit `configuration.manage` ne sert qu'à lire la configuration du dépôt ; les
// décisions de contrôle viennent du serveur (`allowed_reviews`), pas du rôle.
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({
    can: () => false,
    me: { username: "df.innov" },
  }),
}))

vi.mock("@/lib/accounts", () => ({
  fetchConfiguration: vi.fn(),
}))

/** Une pièce telle que le serveur la rend ; chaque test pose `allowed_reviews`. */
function piece(overrides: Partial<Proof>): Proof {
  return {
    id: 1,
    dossier: 3,
    original_name: "facture.pdf",
    kind: "invoice",
    kind_display: "Facture",
    status: "received",
    status_display: "Reçu",
    is_complete: true,
    sha256: "abcdef0123456789",
    size: 1024,
    content_type: "application/pdf",
    version: 1,
    replaces: null,
    uploaded_by: "togo.innov",
    rejection_reason: "",
    download_url: "/api/proofs/1/download/",
    allowed_reviews: [],
    created_at: "2026-03-15T10:00:00Z",
    updated_at: "2026-03-15T10:00:00Z",
    ...overrides,
  } as Proof
}

function afficher(proofs: Proof[], props: Partial<Parameters<typeof ProofPanel>[0]> = {}) {
  return render(
    <ProofPanel dossierId={3} proofs={proofs} canUpload={false} onChanged={vi.fn()} {...props} />,
  )
}

describe("ProofPanel — contrôle documentaire", () => {
  it("propose les décisions que le serveur autorise, sans archivage", () => {
    afficher([piece({ allowed_reviews: ["validated", "rejected"] })])

    fireEvent.click(screen.getByRole("button", { name: "Contrôler facture.pdf" }))

    const options = screen.getAllByRole("option").map((o) => o.textContent)
    expect(options).toEqual(["Valider la pièce", "Rejeter"])
  })

  it("masque « Contrôler » quand le serveur n'ouvre aucune décision", () => {
    afficher([piece({ allowed_reviews: [] })])

    expect(screen.queryByRole("button", { name: "Contrôler facture.pdf" })).toBeNull()
  })

  it("ne propose jamais « Archiver », même si le serveur l'ouvrait : l'archivage accompagne un remplacement", () => {
    afficher([piece({ allowed_reviews: ["validated", "archived"] })])

    fireEvent.click(screen.getByRole("button", { name: "Contrôler facture.pdf" }))

    const options = screen.getAllByRole("option").map((o) => o.textContent)
    expect(options).toEqual(["Valider la pièce"])
  })

  it("garde l'ordre du dialogue, quel que soit celui du serveur", () => {
    afficher([piece({ allowed_reviews: ["rejected", "incomplete", "to_review", "validated"] })])

    fireEvent.click(screen.getByRole("button", { name: "Contrôler facture.pdf" }))

    const options = screen.getAllByRole("option").map((o) => o.textContent)
    expect(options).toEqual(["Valider la pièce", "À contrôler", "Marquer incomplet", "Rejeter"])
  })
})

describe("ProofPanel — dépôt", () => {
  it("propose le dépôt tant que le dossier n'est pas clôturé", () => {
    afficher([], { canUpload: true })

    expect(screen.getByRole("button", { name: "Déposer" })).toBeInTheDocument()
    expect(screen.getByText(/Déposez la facture/)).toBeInTheDocument()
  })

  it("dit que le dossier est clôturé plutôt que d'inviter à déposer", () => {
    afficher([], { canUpload: false, closed: true })

    expect(screen.queryByRole("button", { name: "Déposer" })).toBeNull()
    expect(screen.getByText(/clôturé/)).toBeInTheDocument()
  })
})
