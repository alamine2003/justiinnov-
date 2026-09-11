import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { RequestRectification } from "@/components/expenses/request-rectification"
import { ApiError } from "@/lib/api"
import type { Expense } from "@/lib/types"

/**
 * Le serveur dit s'il accepterait la demande (`allowed_actions`) : droit,
 * ligne justifiée ou clôturée, aucune demande déjà en attente. Le composant
 * ne lit rien d'autre.
 */
function ligne(allowedActions: string[]): Expense {
  return {
    id: 7,
    title: "Hôtel Sarakawa",
    status: "justified",
    status_display: "Justifié",
    allowed_actions: allowedActions,
  } as unknown as Expense
}

describe("RequestRectification — visibilité", () => {
  it("s'affiche quand le serveur ouvre la demande", () => {
    render(
      <RequestRectification expense={ligne(["close", "request_rectification"])} onRequest={vi.fn()} />,
    )

    expect(screen.getByRole("button", { name: "Rectifier" })).toBeInTheDocument()
  })

  it("reste absent quand le serveur ne l'ouvre pas", () => {
    render(<RequestRectification expense={ligne(["close"])} onRequest={vi.fn()} />)

    expect(screen.queryByRole("button", { name: "Rectifier" })).toBeNull()
  })
})

describe("RequestRectification — dialogue", () => {
  it("exige un motif sans appeler le serveur", () => {
    const onRequest = vi.fn()
    render(<RequestRectification expense={ligne(["request_rectification"])} onRequest={onRequest} />)

    fireEvent.click(screen.getByRole("button", { name: "Rectifier" }))
    expect(screen.getByRole("dialog")).toHaveTextContent("Hôtel Sarakawa")
    fireEvent.click(screen.getByRole("button", { name: "Demander" }))

    expect(screen.getByRole("alert")).toHaveTextContent("motiv")
    expect(onRequest).not.toHaveBeenCalled()
  })

  it("transmet le motif et se referme", async () => {
    const onRequest = vi.fn().mockResolvedValue(undefined)
    render(<RequestRectification expense={ligne(["request_rectification"])} onRequest={onRequest} />)

    fireEvent.click(screen.getByRole("button", { name: "Rectifier" }))
    fireEvent.change(screen.getByLabelText("Motif"), {
      target: { value: "  Le montant justifie est faux  " },
    })
    fireEvent.click(screen.getByRole("button", { name: "Demander" }))

    await waitFor(() => expect(onRequest).toHaveBeenCalledWith("Le montant justifie est faux"))
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull())
  })

  it("affiche les refus du serveur sur la ligne et reste ouvert", async () => {
    const onRequest = vi.fn().mockRejectedValue(
      new ApiError(400, "Une demande est deja en attente.", {
        expense: ["Une demande est deja en attente."],
      }),
    )
    render(<RequestRectification expense={ligne(["request_rectification"])} onRequest={onRequest} />)

    fireEvent.click(screen.getByRole("button", { name: "Rectifier" }))
    fireEvent.change(screen.getByLabelText("Motif"), { target: { value: "Motif" } })
    fireEvent.click(screen.getByRole("button", { name: "Demander" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Une demande est deja en attente.")
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    expect(screen.getByLabelText("Motif")).toHaveValue("Motif")
  })

  it("rattache un refus du motif au champ", async () => {
    const onRequest = vi.fn().mockRejectedValue(
      new ApiError(400, "Motif : trop court.", { motif: ["Trop court."] }),
    )
    render(<RequestRectification expense={ligne(["request_rectification"])} onRequest={onRequest} />)

    fireEvent.click(screen.getByRole("button", { name: "Rectifier" }))
    fireEvent.change(screen.getByLabelText("Motif"), { target: { value: "x" } })
    fireEvent.click(screen.getByRole("button", { name: "Demander" }))

    expect(await screen.findByRole("alert")).toHaveTextContent("Trop court.")
    expect(screen.getByLabelText("Motif")).toHaveAttribute("aria-invalid", "true")
  })
})
