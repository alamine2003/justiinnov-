import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { MatriceDesDroits } from "./permissions-section"
import type { PermissionMatrix } from "@/lib/types"

// jsdom n'a pas d'événement pointeur ; l'interrupteur de base-ui en construit
// un au clic. Un MouseEvent en tient lieu, le test ne lit que l'état.
if (typeof window.PointerEvent === "undefined") {
  Object.defineProperty(window, "PointerEvent", { value: MouseEvent, writable: true })
}

const refreshProfile = vi.fn(async () => {})
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({ can: () => true, me: { role: "admin" }, refreshProfile }),
}))

const updatePermissionMatrix = vi.fn()
vi.mock("@/lib/accounts", () => ({
  fetchPermissionMatrix: vi.fn(),
  fetchConfiguration: vi.fn(),
  updatePermissionMatrix: (...args: unknown[]) => updatePermissionMatrix(...args),
  updateWorkflowConfiguration: vi.fn(),
}))

/** La matrice telle que le serveur la rend : deux droits, deux verrous. */
function matrice(overrides: Partial<PermissionMatrix> = {}): PermissionMatrix {
  return {
    roles: [
      { value: "super_admin", label: "Super administrateur", siege: true, always_global: true },
      { value: "admin", label: "Administrateur (RH)", siege: true, always_global: true },
      { value: "dm", label: "DM", siege: true, always_global: false },
      { value: "manager", label: "Manager (pays)", siege: false, always_global: false },
    ],
    capabilities: [
      {
        key: "data.export",
        group: "Fichiers",
        label: "Exporter",
        description: "Télécharger le registre.",
        roles: ["admin", "super_admin"],
        default_roles: ["admin", "super_admin"],
        fixed_roles: ["super_admin"],
        locked_roles: [],
        settable_by_roles: ["admin", "super_admin"],
      },
      {
        key: "expenses.validate",
        group: "Contrôle",
        label: "Justifier ou refuser",
        description: "Constater.",
        roles: ["admin", "df", "super_admin"],
        default_roles: ["admin", "df", "super_admin"],
        fixed_roles: ["super_admin"],
        locked_roles: ["manager"],
        settable_by_roles: ["admin", "super_admin"],
      },
    ],
    note: "Le super administrateur garde tout.",
    ...overrides,
  }
}

describe("MatriceDesDroits", () => {
  beforeEach(() => {
    updatePermissionMatrix.mockReset()
    refreshProfile.mockClear()
  })

  it("fige les cases verrouillées et laisse les autres basculer", () => {
    render(<MatriceDesDroits matrix={matrice()} onSaved={() => {}} />)

    // Le super administrateur a tout : aucun interrupteur pour lui.
    expect(
      screen.queryByRole("switch", { name: "Exporter pour Super administrateur" }),
    ).not.toBeInTheDocument()
    // Le pays ne justifie jamais : pas d'interrupteur non plus.
    expect(
      screen.queryByRole("switch", { name: "Justifier ou refuser pour Manager (pays)" }),
    ).not.toBeInTheDocument()
    // Le DM peut recevoir l'export : la case existe, décochée.
    expect(screen.getByRole("switch", { name: "Exporter pour DM" })).toHaveAttribute(
      "aria-checked",
      "false",
    )
    expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled()
  })

  it("n'envoie que les capacités modifiées, puis rafraîchit le profil", async () => {
    const onSaved = vi.fn()
    updatePermissionMatrix.mockResolvedValue(matrice())
    render(<MatriceDesDroits matrix={matrice()} onSaved={onSaved} />)

    fireEvent.click(screen.getByRole("switch", { name: "Exporter pour DM" }))
    expect(screen.getByText("1 modification non enregistrée")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    expect(updatePermissionMatrix).toHaveBeenCalledWith({
      "data.export": ["admin", "super_admin", "dm"],
    })
    expect(refreshProfile).toHaveBeenCalled()
  })

  it("tient l'enregistrement pour acquis même si le profil ne se relit pas", async () => {
    const onSaved = vi.fn()
    updatePermissionMatrix.mockResolvedValue(matrice())
    refreshProfile.mockRejectedValueOnce(new Error("panne"))
    render(<MatriceDesDroits matrix={matrice()} onSaved={onSaved} />)

    fireEvent.click(screen.getByRole("switch", { name: "Exporter pour DM" }))
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    await waitFor(() => expect(onSaved).toHaveBeenCalled())
    expect(screen.queryByText("Enregistrement impossible")).not.toBeInTheDocument()
  })

  it("rétablit le défaut d'une ligne écartée", () => {
    const base = matrice()
    const ecartee = matrice({
      capabilities: [
        { ...base.capabilities[0], roles: ["admin", "dm", "super_admin"] },
        base.capabilities[1],
      ],
    })
    render(<MatriceDesDroits matrix={ecartee} onSaved={() => {}} />)

    fireEvent.click(screen.getByRole("button", { name: "Rétablir le défaut pour Exporter" }))

    expect(screen.getByRole("switch", { name: "Exporter pour DM" })).toHaveAttribute(
      "aria-checked",
      "false",
    )
    expect(screen.getByText("1 modification non enregistrée")).toBeInTheDocument()
  })

  it("affiche le refus du serveur sur la ligne concernée", async () => {
    const { ApiError } = await import("@/lib/api")
    updatePermissionMatrix.mockRejectedValue(
      new ApiError(400, "Requête invalide", { "data.export": ["Ce droit ne se retire pas à : Super administrateur."] }),
    )
    render(<MatriceDesDroits matrix={matrice()} onSaved={() => {}} />)

    fireEvent.click(screen.getByRole("switch", { name: "Exporter pour DM" }))
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }))

    expect(
      await screen.findByText("Ce droit ne se retire pas à : Super administrateur."),
    ).toBeInTheDocument()
  })
})
