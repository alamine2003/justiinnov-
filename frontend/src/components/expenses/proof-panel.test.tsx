import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ProofPanel } from "./proof-panel"
import type { Proof } from "@/lib/types"

// Le droit `configuration.manage` ne sert qu'à lire la configuration du dépôt ; les
// décisions de contrôle viennent du serveur (`allowed_reviews`), pas du rôle.
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({
    can: () => false,
    me: { username: "rh.innov" },
  }),
}))

vi.mock("@/lib/accounts", () => ({
  fetchConfiguration: vi.fn(),
}))

const uploadProof = vi.fn()
vi.mock("@/lib/expenses", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/expenses")>()),
  uploadProof: (...args: unknown[]) => uploadProof(...args),
}))

/** Une pièce telle que le serveur la rend ; chaque test pose `allowed_reviews`. */
function piece(overrides: Partial<Proof>): Proof {
  return {
    id: 1,
    dossier: 3,
    expense: 9,
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
    <ProofPanel expenseId={9} proofs={proofs} canUpload={false} onChanged={vi.fn()} {...props} />,
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

describe("ProofPanel — la pièce d'une ligne (décision 107)", () => {
  it("dépose sur la ligne : la charge utile porte la ligne, pas le dossier", async () => {
    uploadProof.mockResolvedValue({})
    const onChanged = vi.fn().mockResolvedValue(undefined)
    afficher([], { canUpload: true, compact: true, onChanged })

    fireEvent.click(screen.getByRole("button", { name: "Déposer" }))
    const fichier = new File(["%PDF-1.4"], "taxi.pdf", { type: "application/pdf" })
    fireEvent.change(screen.getByLabelText("Fichier"), { target: { files: [fichier] } })
    fireEvent.click(screen.getAllByRole("button", { name: "Déposer" }).at(-1)!)

    await waitFor(() => expect(uploadProof).toHaveBeenCalled())
    const form = uploadProof.mock.calls[0][0] as FormData
    expect(form.get("expense")).toBe("9")
    expect(form.has("dossier")).toBe(false)
    expect(onChanged).toHaveBeenCalled()
  })

  it("ne remplace que les pièces de la ligne", () => {
    afficher([piece({ id: 1, original_name: "taxi.pdf" })], { canUpload: true, compact: true })

    fireEvent.click(screen.getByRole("button", { name: "Déposer une autre pièce" }))

    expect(screen.getByRole("option", { name: "taxi.pdf (v1)" })).toBeInTheDocument()
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toContain("Nouveau justificatif")
  })

  it("montre au pays le motif du rejet de la pièce de sa ligne", () => {
    afficher(
      [piece({ status: "rejected", status_display: "Rejeté", rejection_reason: "Illisible" })],
      { compact: true },
    )

    expect(screen.getByText("Rejetée : Illisible")).toBeInTheDocument()
  })

  it("ne propose pas le dépôt sans `upload` sur la ligne", () => {
    afficher([piece({})], { canUpload: false, compact: true })

    expect(screen.queryByRole("button", { name: /Déposer/ })).toBeNull()
    expect(screen.getByText("facture.pdf")).toBeInTheDocument()
  })

  it("ne dépose jamais sur les pièces d'avant la 2.0, rangées sur le dossier", () => {
    afficher([piece({ expense: null })], { canUpload: true, expenseId: null })

    expect(screen.queryByRole("button", { name: "Déposer" })).toBeNull()
    expect(screen.getByText("Pièces d'avant la 2.0")).toBeInTheDocument()
  })
})
