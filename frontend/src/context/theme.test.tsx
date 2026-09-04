import { act, fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ThemeProvider } from "@/context/theme"
import { useTheme } from "@/context/use-theme"

type Abonne = (event: { matches: boolean }) => void

function simulerSysteme(sombre: boolean) {
  const abonnes = new Set<Abonne>()
  const media = {
    matches: sombre,
    addEventListener: vi.fn((_: string, fn: Abonne) => abonnes.add(fn)),
    removeEventListener: vi.fn((_: string, fn: Abonne) => abonnes.delete(fn)),
    addListener: vi.fn(),
    removeListener: vi.fn(),
  }
  vi.stubGlobal("matchMedia", () => media)
  return {
    basculer(versSombre: boolean) {
      media.matches = versSombre
      abonnes.forEach((fn) => fn({ matches: versSombre }))
    },
  }
}

function Sonde() {
  const { theme, resolved, setTheme } = useTheme()
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="resolved">{resolved}</span>
      <button onClick={() => setTheme("dark")}>Sombre</button>
    </div>
  )
}

describe("ThemeProvider", () => {
  beforeEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    document.documentElement.classList.remove("dark")
    document.documentElement.style.colorScheme = ""
  })

  it("applique le choix enregistré au montage", () => {
    localStorage.setItem("justi_theme", "dark")

    render(
      <ThemeProvider>
        <Sonde />
      </ThemeProvider>,
    )

    expect(document.documentElement.classList.contains("dark")).toBe(true)
  })

  it("enregistre le nouveau choix", () => {
    render(
      <ThemeProvider>
        <Sonde />
      </ThemeProvider>,
    )

    fireEvent.click(screen.getByRole("button", { name: "Sombre" }))

    expect(localStorage.getItem("justi_theme")).toBe("dark")
    expect(document.documentElement.classList.contains("dark")).toBe(true)
  })

  it("suit le système quand le choix est « système »", () => {
    simulerSysteme(true)

    render(
      <ThemeProvider>
        <Sonde />
      </ThemeProvider>,
    )

    expect(screen.getByTestId("theme")).toHaveTextContent("system")
    expect(screen.getByTestId("resolved")).toHaveTextContent("dark")
  })

  it("met `resolved` à jour quand le système change de thème", () => {
    // Un changement de thème système en soirée restait clair jusqu'au
    // prochain rechargement : la classe changeait mais pas la valeur exposée,
    // et l'icône du sélecteur mentait.
    const systeme = simulerSysteme(false)

    render(
      <ThemeProvider>
        <Sonde />
      </ThemeProvider>,
    )
    expect(screen.getByTestId("resolved")).toHaveTextContent("light")

    act(() => systeme.basculer(true))

    expect(screen.getByTestId("resolved")).toHaveTextContent("dark")
    expect(document.documentElement.classList.contains("dark")).toBe(true)
  })

  it("ignore le système quand un thème est imposé", () => {
    const systeme = simulerSysteme(false)
    localStorage.setItem("justi_theme", "light")

    render(
      <ThemeProvider>
        <Sonde />
      </ThemeProvider>,
    )
    act(() => systeme.basculer(true))

    expect(screen.getByTestId("resolved")).toHaveTextContent("light")
    expect(document.documentElement.classList.contains("dark")).toBe(false)
  })

  it("lève hors du provider", () => {
    vi.spyOn(console, "error").mockImplementation(() => {})

    expect(() => render(<Sonde />)).toThrow(
      "useTheme doit être utilisé dans un ThemeProvider",
    )
  })
})
