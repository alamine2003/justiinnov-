import { beforeEach, describe, expect, it, vi } from "vitest"
import {
  applyTheme,
  readStoredTheme,
  resolveTheme,
  storeTheme,
} from "@/lib/theme"

function simulerSysteme(sombre: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: sombre,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    // Anciennes API, encore attendues par certaines bibliothèques.
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
    onchange: null,
  }))
}

function simulerStockageEnPanne() {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("stockage indisponible")
  })
}

describe("readStoredTheme", () => {
  beforeEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    document.documentElement.classList.remove("dark")
    document.documentElement.style.colorScheme = ""
  })

  it("renvoie le choix enregistré", () => {
    localStorage.setItem("justi_theme", "dark")

    expect(readStoredTheme()).toBe("dark")
  })

  it("retombe sur « système » sans choix enregistré", () => {
    expect(readStoredTheme()).toBe("system")
  })

  it("ignore une valeur corrompue", () => {
    localStorage.setItem("justi_theme", "bleu")

    expect(readStoredTheme()).toBe("system")
  })

  it("survit à un stockage indisponible", () => {
    simulerStockageEnPanne()

    expect(readStoredTheme()).toBe("system")
  })
})

describe("storeTheme", () => {
  beforeEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it("enregistre le choix", () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem")

    storeTheme("dark")

    expect(setItem).toHaveBeenCalledWith("justi_theme", "dark")
  })

  it("n'échoue pas si le stockage refuse d'écrire", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("écriture refusée")
    })

    expect(() => storeTheme("dark")).not.toThrow()
  })
})

describe("resolveTheme", () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it("« clair » et « sombre » s'imposent", () => {
    simulerSysteme(true)

    expect(resolveTheme("dark")).toBe("dark")
    expect(resolveTheme("light")).toBe("light")
  })

  it("« système » suit la préférence du système", () => {
    simulerSysteme(true)
    expect(resolveTheme("system")).toBe("dark")

    simulerSysteme(false)
    expect(resolveTheme("system")).toBe("light")
  })
})

describe("applyTheme", () => {
  beforeEach(() => {
    document.documentElement.classList.remove("dark")
    document.documentElement.style.colorScheme = ""
  })

  it("pose la classe sombre sur la racine", () => {
    applyTheme("dark")

    expect(document.documentElement.classList.contains("dark")).toBe(true)
  })

  it("retire la classe en mode clair", () => {
    applyTheme("dark")
    applyTheme("light")

    expect(document.documentElement.classList.contains("dark")).toBe(false)
  })

  it("tient color-scheme à jour", () => {
    applyTheme("dark")
    expect(document.documentElement.style.colorScheme).toBe("dark")

    applyTheme("light")
    expect(document.documentElement.style.colorScheme).toBe("light")
  })
})
