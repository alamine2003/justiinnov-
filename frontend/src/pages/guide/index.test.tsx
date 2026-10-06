import { existsSync, readFileSync } from "node:fs"
import { join } from "node:path"
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import i18n from "@/i18n"
import { GUIDES, LANGUES_DES_GUIDES } from "@/lib/guides"
import { GuidePage } from "."

let droits = new Set<string>()
vi.mock("@/context/use-auth", () => ({
  useAuth: () => ({ can: (cle: string) => droits.has(cle) }),
}))

const MANAGER = ["projets.create", "expenses.create", "proofs.upload", "dossiers.submit", "data.import"]

function Adresse() {
  const location = useLocation()
  return <output aria-label="adresse">{location.search}</output>
}

function monter(chemin = "/guide") {
  return render(
    <MemoryRouter initialEntries={[chemin]}>
      <Routes>
        <Route path="/guide" element={<><GuidePage /><Adresse /></>} />
      </Routes>
    </MemoryRouter>,
  )
}

const source = (conteneur: HTMLElement) => conteneur.querySelector("video source")?.getAttribute("src")

/** Les fichiers statiques servis tels quels (vitest tourne dans `frontend/`). */
const PUBLIC = join(process.cwd(), "public")

/** Le fichier statique tel que nginx le sert, lu dans `public/`. */
function servirLesGuides(adresse: string) {
  const fichier = join(PUBLIC, adresse)
  if (!existsSync(fichier)) return Promise.resolve(new Response("", { status: 404 }))
  return Promise.resolve(new Response(readFileSync(fichier, "utf8"), { status: 200 }))
}

/** Les répliques d'un fichier tourné, lues sans l'analyseur de la page : tout ce qui n'est ni en-tête, ni numéro, ni horodatage. */
function repliques(langue: string, id: string) {
  return readFileSync(join(PUBLIC, "guides", langue, `${id}.vtt`), "utf8")
    .split("\n")
    .filter((ligne) => ligne.trim() && ligne !== "WEBVTT" && !/^\d+$/.test(ligne) && !ligne.includes("-->"))
}

function servir(contenu: string, status = 200) {
  vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(contenu, { status }))))
}

async function etapes() {
  const section = await screen.findByRole("region", { name: /Les étapes|The steps/ })
  return within(section)
    .getAllByRole("listitem")
    .map((item) => item.textContent)
}

beforeEach(() => {
  droits = new Set(MANAGER)
  vi.stubGlobal("fetch", vi.fn((adresse: string) => servirLesGuides(adresse)))
})
afterEach(async () => {
  vi.unstubAllGlobals()
  await i18n.changeLanguage("fr")
})

/** Décision 118 : un guide par geste, dans la langue de l'interface, à qui a la capacité. */
describe("GuidePage", () => {
  it("liste les guides du manager dans l'ordre et ouvre le premier, sous-titré", () => {
    const { container } = monter()

    const sommaire = screen.getByRole("navigation", { name: "Les guides" })
    expect(Array.from(sommaire.querySelectorAll("button")).map((b) => b.getAttribute("aria-label"))).toEqual([
      "1. Ouvrir un projet",
      "2. Saisir une dépense",
      "3. Joindre une pièce",
      "4. Soumettre un dossier",
      "5. Importer un classeur",
    ])
    expect(screen.getByRole("button", { name: "1. Ouvrir un projet" })).toHaveAttribute("aria-current", "true")
    expect(source(container)).toBe("/guides/fr/ouvrir-un-projet.webm")
    const piste = container.querySelector("video track")
    expect(piste).toHaveAttribute("src", "/guides/fr/ouvrir-un-projet.vtt")
    expect(piste).toHaveAttribute("srclang", "fr")
    expect(piste).toHaveAttribute("default")
  })

  it("change de vidéo au choix d'un guide, et le garde dans l'adresse", () => {
    const { container } = monter()

    fireEvent.click(screen.getByRole("button", { name: "3. Joindre une pièce" }))

    expect(source(container)).toBe("/guides/fr/joindre-une-piece.webm")
    expect(screen.getByRole("heading", { name: "Joindre une pièce" })).toBeInTheDocument()
    expect(screen.getByLabelText("adresse")).toHaveTextContent("?video=joindre-une-piece")
  })

  it("rouvre le guide de l'adresse, et le premier si l'adresse en nomme un inconnu", () => {
    const { container, unmount } = monter("/guide?video=importer-un-classeur")
    expect(source(container)).toBe("/guides/fr/importer-un-classeur.webm")
    unmount()

    const autre = monter("/guide?video=inconnu")
    expect(source(autre.container)).toBe("/guides/fr/ouvrir-un-projet.webm")
  })

  it("ne montre pas le guide d'un geste fermé au compte", () => {
    droits = new Set(["expenses.create"])

    monter()

    expect(screen.getByRole("button", { name: "1. Saisir une dépense" })).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Importer un classeur/ })).toBeNull()
  })

  it("suit la langue de l'interface : vidéo, sous-titres et titres en anglais", async () => {
    await i18n.changeLanguage("en")

    const { container } = monter()

    expect(source(container)).toBe("/guides/en/ouvrir-un-projet.webm")
    expect(container.querySelector("video track")).toHaveAttribute("srclang", "en")
    expect(container.querySelector("video")).toHaveAttribute("poster", "/guides/en/ouvrir-un-projet.jpg")
    expect(screen.getByRole("heading", { name: "Open a project" })).toBeInTheDocument()
  })

  it("nomme la vidéo par le titre du guide ouvert", () => {
    const { container } = monter()

    const video = container.querySelector("video")!
    expect(document.getElementById(video.getAttribute("aria-labelledby")!)).toHaveTextContent("Ouvrir un projet")
  })

  it("borne le lecteur à la hauteur de page, sans descendre sous 52 rem de large", () => {
    // Pleine largeur, la vidéo (16/10) passait sous la ligne de flottaison à
    // 1366×768 : ses contrôles ne se voyaient pas sans défiler. jsdom ne
    // mesure rien ; les mesures réelles sont dans DESIGN.md, « Guide vidéo ».
    const { container } = monter()

    const video = container.querySelector("video")!
    expect(video).toHaveClass("w-full", "aspect-[16/10]")
    const cadre = video.parentElement!
    expect(cadre).toHaveClass("mx-auto", "w-full", "max-w-[max(52rem,calc((var(--hauteur-page)_-_7.5rem)*1.6))]")
    // Titre et étapes s'alignent sur la vidéo, dans le même cadre.
    expect(within(cadre).getByRole("heading", { name: "Ouvrir un projet" })).toBeInTheDocument()
  })

  it("dit à un compte sans guide pourquoi la page est vide", () => {
    droits = new Set(["audit.read"])

    const { container } = monter()

    expect(screen.getByText("Aucun guide pour votre compte")).toBeInTheDocument()
    expect(container.querySelector("video")).toBeNull()
  })

  it("donne en texte les étapes du guide ouvert, lues dans ses sous-titres", async () => {
    // Vidéo muette : sans cette liste, les étapes n'existaient que dans la
    // piste de sous-titres, ni relisibles ni cherchables.
    monter()

    expect(await etapes()).toEqual(repliques("fr", "ouvrir-un-projet"))
    expect(fetch).toHaveBeenCalledWith("/guides/fr/ouvrir-un-projet.vtt", expect.anything())

    fireEvent.click(screen.getByRole("button", { name: "4. Soumettre un dossier" }))
    await waitFor(async () => expect(await etapes()).toEqual(repliques("fr", "soumettre-un-dossier")))
  })

  it("lit les étapes dans les sous-titres anglais quand l'interface est en anglais", async () => {
    await i18n.changeLanguage("en")

    monter("/guide?video=joindre-une-piece")

    expect(await etapes()).toEqual(repliques("en", "joindre-une-piece"))
  })

  it("chaque guide filmé a des étapes à lire, en français et en anglais", () => {
    for (const langue of LANGUES_DES_GUIDES) {
      for (const { id } of GUIDES) {
        expect(repliques(langue, id).length, `${langue}/${id}`).toBeGreaterThan(0)
      }
    }
  })

  it("analyse le WebVTT : identifiant facultatif, réglages, NOTE et STYLE, plusieurs lignes, balises et entités", async () => {
    servir(
      "\uFEFFWEBVTT - guide\r\nKind: captions\r\n\r\n" +
        "NOTE tourné par le script\r\n\r\n" +
        "STYLE\r\n::cue { color: white }\r\n\r\n" +
        "00:00:01.000 --> 00:00:02.000 line:90%\r\nOuvrez le <b>dossier</b>\r\nde votre pays.\r\n\r\n" +
        "deux\r\n00:02.000 --> 00:03.000\r\n<v Guide>Frais &amp; débours &lt;TTC&gt;</v>\r\n",
    )

    monter()

    expect(await etapes()).toEqual(["Ouvrez le dossier de votre pays.", "Frais & débours <TTC>"])
  })

  it("n'affiche rien si le fichier n'est pas un sous-titre, ou s'il manque", async () => {
    // Le serveur de développement répond la page de l'application à une
    // adresse inconnue ; nginx répond 404.
    servir("<!doctype html><html></html>")
    const { unmount } = monter()
    await waitFor(() => expect(fetch).toHaveBeenCalled())
    await waitFor(() => expect(screen.queryByText("Chargement des étapes…")).toBeNull())
    expect(screen.queryByRole("region", { name: "Les étapes" })).toBeNull()
    expect(screen.queryByRole("alert")).toBeNull()
    unmount()

    servir("", 404)
    monter()
    await waitFor(() => expect(screen.queryByText("Chargement des étapes…")).toBeNull())
    expect(screen.queryByRole("region", { name: "Les étapes" })).toBeNull()
    expect(screen.queryByRole("alert")).toBeNull()
  })

  it("dit discrètement le chargement des étapes, puis leur échec", async () => {
    servir("", 500)

    monter()

    // Annoncé sans interrompre (`<output>`, rôle status).
    expect(screen.getByText("Chargement des étapes…").tagName).toBe("OUTPUT")
    expect(await screen.findByRole("alert")).toHaveTextContent("Les étapes n'ont pas pu être chargées")
    // Le lecteur, lui, reste : les sous-titres donnent les mêmes étapes.
    expect(screen.getByRole("heading", { name: "Ouvrir un projet" })).toBeInTheDocument()
  })
})
