import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { Table, TableBody, TableCell, TableDefilante, TableRow } from "./table"

/** Un tableau qui défile s'atteint au clavier, même sans lien (décision 129). */
describe("TableDefilante", () => {
  it("est une région nommée, focalisable", () => {
    render(
      <TableDefilante label="Registre">
        <Table>
          <TableBody>
            <TableRow>
              <TableCell>texte seul</TableCell>
            </TableRow>
          </TableBody>
        </Table>
      </TableDefilante>,
    )

    const region = screen.getByRole("region", { name: "Registre" })
    expect(region).toHaveAttribute("tabindex", "0")
    expect(region).toHaveClass("defile", "overflow-x-auto")
  })
})
