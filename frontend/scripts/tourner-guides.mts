/**
 * Tourne les guides vidéo (décision 118) : chaque parcours de
 * `src/lib/guides.ts`, joué par un manager sur une base jetable. Pour chaque
 * guide, le script écrit dans `public/guides/<langue>/` la vidéo (`.webm`),
 * ses sous-titres (`.vtt`) et son affiche (`.jpg`) — seulement si tout le
 * tournage a réussi : un guide qui échoue ne remplace rien.
 *
 * Une langue par exécution, sur une base neuve : le tournage écrit dans la
 * base (un projet, une ligne, une pièce, une soumission, un import), et le
 * tournage anglais montrerait sinon le projet du tournage français. La
 * procédure complète est dans le README (« Guides vidéo ») :
 *
 *   GUIDES_LANGUE=fr SHOT_BASE=http://localhost:5173 \
 *   SHOT_COUNTRY_USER=… SHOT_COUNTRY_PASSWORD=… SHOT_COUNTRY_TOTP_SECRET=… \
 *   npx tsx scripts/tourner-guides.mts
 *
 * Le compte est un `manager` du Togo sans équipe imposée, sur les données
 * de `manage.py seed_demo --base-jetable` (équipe « Équipe Kara », manager
 * responsable « Kodjo Mensah »). Comme les captures, le script échoue sur
 * toute erreur de console, et sur tout geste qui n'aboutit pas.
 */
import { execFile } from "node:child_process"
import { existsSync, readdirSync } from "node:fs"
import { copyFile, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import { homedir, tmpdir } from "node:os"
import path from "node:path"
import { promisify } from "node:util"
import { chromium, type Browser, type Page } from "playwright"
import { GUIDES, LANGUES_DES_GUIDES, type IdDeGuide, type LangueDeGuide } from "../src/lib/guides.ts"
import { classeur } from "./guides/classeur.ts"
import { POINTEUR, Scene, sousTitres } from "./guides/scene.ts"
import { credentials, estLeRefusAttenduDuCode, signIn } from "./login.ts"

const BASE = process.env.SHOT_BASE ?? "http://localhost:5173"
const SORTIE = process.env.GUIDES_OUT ?? path.resolve(import.meta.dirname, "../public/guides")
const TAILLE = { width: 1280, height: 800 }

/** La langue du tournage : obligatoire, une seule par base neuve. */
function langueDuTournage(): LangueDeGuide {
  const langue = process.env.GUIDES_LANGUE
  if (!langue || !(LANGUES_DES_GUIDES as readonly string[]).includes(langue)) {
    throw new Error(`GUIDES_LANGUE doit valoir ${LANGUES_DES_GUIDES.join(" ou ")}, une langue par base neuve.`)
  }
  return langue as LangueDeGuide
}

/**
 * `GUIDES_SEULS=saisir-une-ligne,…` restreint le tournage, le temps de
 * mettre un guide au point : chaque guide reprend ce que le précédent a
 * créé (le projet, la ligne, la pièce), un guide seul se tourne donc sur
 * une base où les précédents ont déjà été joués. Un nom inconnu arrête
 * tout, plutôt que de ne rien tourner sans le dire.
 */
function guidesDuTournage(): IdDeGuide[] {
  const tous = GUIDES.map((guide) => guide.id)
  const demandes = process.env.GUIDES_SEULS?.split(",").filter(Boolean)
  if (!demandes) return tous
  const inconnus = demandes.filter((id) => !(tous as string[]).includes(id))
  if (inconnus.length) throw new Error(`Guides inconnus : ${inconnus.join(", ")}. Connus : ${tous.join(", ")}.`)
  return tous.filter((id) => demandes.includes(id))
}

/**
 * Le ffmpeg qui réencode les prises. Playwright filme vite et lourd (VP8 à
 * 25 images par seconde, environ 2 Mo pour 40 secondes) ; un écran qui
 * bouge peu se réencode au quart, sans perdre la lisibilité du texte. Le
 * ffmpeg livré avec les navigateurs de Playwright suffit (il lit et écrit
 * le WebM) ; `GUIDES_FFMPEG` en désigne un autre.
 */
function ffmpeg() {
  if (process.env.GUIDES_FFMPEG) return process.env.GUIDES_FFMPEG
  const navigateurs =
    process.env.PLAYWRIGHT_BROWSERS_PATH ??
    (process.platform === "darwin"
      ? path.join(homedir(), "Library/Caches/ms-playwright")
      : path.join(homedir(), ".cache/ms-playwright"))
  if (existsSync(navigateurs)) {
    for (const dossier of readdirSync(navigateurs).filter((d) => d.startsWith("ffmpeg-")).sort().reverse()) {
      for (const nom of ["ffmpeg-linux", "ffmpeg-mac", "ffmpeg"]) {
        const chemin = path.join(navigateurs, dossier, nom)
        if (existsSync(chemin)) return chemin
      }
    }
  }
  throw new Error(
    "ffmpeg introuvable : installez-le avec les navigateurs de Playwright, ou désignez-le par GUIDES_FFMPEG.",
  )
}

/** Réencode une prise : 15 images par seconde suffisent à un écran d'application. */
async function reencoder(source: string, cible: string) {
  await promisify(execFile)(ffmpeg(), [
    "-hide_banner", "-loglevel", "error", "-y", "-i", source,
    "-c:v", "libvpx", "-crf", "12", "-b:v", "300k", "-deadline", "good", "-cpu-used", "1",
    "-r", "15", "-an", cible,
  ])
}

/** Les libellés de l'interface, lus dans son dictionnaire : le script clique ce qu'une personne lit. */
async function dictionnaire(langue: LangueDeGuide) {
  const brut = JSON.parse(
    await readFile(path.resolve(import.meta.dirname, `../src/i18n/${langue}.json`), "utf8"),
  ) as Record<string, unknown>
  return (cle: string, valeurs: Record<string, string> = {}) => {
    let texte: unknown = brut
    for (const morceau of cle.split(".")) texte = (texte as Record<string, unknown>)[morceau]
    if (typeof texte !== "string") throw new Error(`Clé absente du dictionnaire ${langue} : ${cle}`)
    return texte.replace(/\{\{(\w+)\}\}/g, (_, nom: string) => valeurs[nom] ?? "")
  }
}

type T = Awaited<ReturnType<typeof dictionnaire>>

/** Ce que le manager saisit, dans la langue du guide. */
const DONNEES = {
  fr: {
    projet: "Congrès de cardiologie 2026",
    ligne: "Pause-café du congrès",
    lieu: "Lomé",
    montant: "85000",
    recu: "Reçu n° 0142 — Pause-café du congrès — 85 000 FCFA",
    fichierRecu: "recu-0142.pdf",
    fichierClasseur: "depenses-stands.xlsx",
    lignesImportees: ["Location du stand", "Impression des kakémonos", "Transport du matériel"],
  },
  en: {
    projet: "Cardiology congress 2026",
    ligne: "Congress coffee break",
    lieu: "Lomé",
    montant: "85000",
    recu: "Receipt No. 0142 — Congress coffee break — 85,000 FCFA",
    fichierRecu: "receipt-0142.pdf",
    fichierClasseur: "stand-expenses.xlsx",
    lignesImportees: ["Stand rental", "Banner printing", "Equipment transport"],
  },
} as const

type Donnees = (typeof DONNEES)[LangueDeGuide]

/**
 * Les légendes de chaque guide : elles deviennent ses sous-titres. Un
 * bouton s'y nomme par son libellé du dictionnaire, comme à l'écran. Elles
 * disent les règles de CLAUDE.md telles qu'elles sont : relisez-les quand
 * une règle du circuit change.
 */
const LEGENDES: Record<IdDeGuide, Record<LangueDeGuide, (t: T) => string[]>> = {
  "ouvrir-un-projet": {
    fr: (t) => [
      "Un projet regroupe les dépenses d'un congrès, d'un voyage ou d'un soutien financier.",
      `Cliquez sur « ${t("projets.liste.nouveau")} ».`,
      "Donnez-lui un nom que vos collègues reconnaîtront.",
      "Choisissez son type : il fixe les dossiers que le projet reçoit d'office.",
      "Choisissez l'équipe : ses dossiers et leurs lignes la porteront.",
      `Cliquez sur « ${t("commun.creer")} ».`,
      "Le projet est ouvert : il a sa référence et ses dossiers, un par type.",
    ],
    en: (t) => [
      "A project groups the spending of a congress, a trip or a financial support.",
      `Click “${t("projets.liste.nouveau")}”.`,
      "Give it a name your colleagues will recognise.",
      "Choose its type: it sets the dossiers the project receives automatically.",
      "Choose the team: its dossiers and their lines will carry it.",
      `Click “${t("commun.creer")}”.`,
      "The project is open: it has its reference and its dossiers, one per type.",
    ],
  },
  "saisir-une-ligne": {
    fr: (t) => [
      "Chaque dossier reçoit les dépenses de son type. Ouvrez celui qui convient.",
      `Cliquez sur « ${t("commun.ajouter")} » pour saisir une dépense.`,
      "Décrivez la dépense : ce qui a été payé, quand et où.",
      "Indiquez le montant, dans la devise du pays.",
      "Choisissez le manager responsable : sans lui, le dossier ne se soumet pas.",
      `Cliquez sur « ${t("commun.enregistrer")} ». La ligne reste un brouillon, modifiable, jusqu'à la soumission.`,
    ],
    en: (t) => [
      "Each dossier receives the expenses of its type. Open the right one.",
      `Click “${t("commun.ajouter")}” to enter an expense.`,
      "Describe the expense: what was paid, when and where.",
      "Enter the amount, in the country's currency.",
      "Choose the manager in charge: without one, the dossier cannot be submitted.",
      `Click “${t("commun.enregistrer")}”. The line stays a draft, still editable, until it is submitted.`,
    ],
  },
  "joindre-une-piece": {
    fr: (t) => [
      "Chaque ligne a sa pièce : le reçu, la facture ou le document qui prouve la dépense.",
      "Déposez la pièce depuis sa ligne.",
      "Choisissez le fichier : un PDF, une image ou un document.",
      `Indiquez de quel type de pièce il s'agit, puis cliquez sur « ${t("pieces.deposer")} ».`,
      "La pièce est rangée sous sa ligne. Le siège la contrôlera.",
    ],
    en: (t) => [
      "Each line has its document: the receipt, invoice or paper that proves the expense.",
      "Upload the document from its line.",
      "Choose the file: a PDF, an image or a document.",
      `Say what kind of document it is, then click “${t("pieces.deposer")}”.`,
      "The document is filed under its line. Head office will review it.",
    ],
  },
  "soumettre-un-dossier": {
    fr: (t) => [
      "Quand les dépenses du dossier sont complètes, avec leurs pièces, soumettez-le.",
      `Cliquez sur « ${t("depenses.circuit.soumettre")} » : toutes les lignes partent avec le dossier.`,
      "Le dossier est soumis : ses lignes ne se modifient plus, le siège les contrôle.",
      "Une pièce oubliée se dépose encore depuis sa ligne, jusqu'à la clôture du dossier.",
    ],
    en: (t) => [
      "When the dossier's expenses are complete, with their documents, submit it.",
      `Click “${t("depenses.circuit.soumettre")}”: every line goes with the dossier.`,
      "The dossier is submitted: its lines can no longer be changed, head office reviews them.",
      "A forgotten document can still be uploaded from its line, until the dossier is closed.",
    ],
  },
  "importer-un-classeur": {
    fr: (t) => [
      "Vos dépenses sont déjà dans un classeur Excel ? Importez-le dans un dossier du projet.",
      "Choisissez le projet, puis le dossier qui recevra les lignes.",
      "Choisissez le classeur.",
      `Simulez d'abord (« ${t("dossiers.import.simuler")} ») : rien n'est écrit, vous voyez ce qui serait créé.`,
      `Tout est correct : désactivez la simulation, puis cliquez sur « ${t("dossiers.import.importer")} ».`,
      "Les lignes arrivent en brouillon dans le dossier. Joignez ensuite la pièce de chacune.",
    ],
    en: (t) => [
      "Are your expenses already in an Excel workbook? Import it into a project dossier.",
      "Choose the project, then the dossier that will receive the lines.",
      "Choose the workbook.",
      `Simulate first (“${t("dossiers.import.simuler")}”): nothing is written, you see what would be created.`,
      `Everything is correct: turn off the simulation, then click “${t("dossiers.import.importer")}”.`,
      "The lines arrive as drafts in the dossier. Then attach each one's document.",
    ],
  },
}

interface Tournage {
  /** La page où commence la vidéo. */
  depart: string
  jouer: (s: Scene, t: T, d: Donnees) => Promise<void>
}

/** Ouvre le dossier D001 du projet du guide, depuis la liste des projets. */
async function ouvrirLeDossier(s: Scene, d: Donnees, montrer = true) {
  for (const cible of [
    s.page.getByRole("link", { name: d.projet }).first(),
    s.page.getByRole("link", { name: /D001/ }).first(),
  ]) {
    if (montrer) await s.cliquer(cible)
    else await cible.click()
    await s.page.waitForLoadState("networkidle")
  }
}

const TOURNAGES: Record<IdDeGuide, Tournage> = {
  "ouvrir-un-projet": {
    depart: "/projets",
    async jouer(s, t, d) {
      await s.dire(0)
      await s.dire(1)
      await s.cliquer(s.page.getByRole("button", { name: t("projets.liste.nouveau") }))
      const dialogue = s.page.getByRole("dialog")
      await s.dire(2)
      await s.saisir(dialogue.locator("#projet-name"), d.projet)
      await s.dire(3)
      await s.choisir(dialogue.locator("#projet-kind"), { index: 1 })
      await s.dire(4)
      await s.choisir(dialogue.locator("#projet-team"), { index: 1 })
      await s.dire(5)
      await s.cliquer(dialogue.getByRole("button", { name: t("commun.creer") }))
      await s.page.getByRole("heading", { name: d.projet }).waitFor()
      await s.dire(6)
    },
  },
  "saisir-une-ligne": {
    depart: "/projets",
    async jouer(s, t, d) {
      await s.dire(0)
      await ouvrirLeDossier(s, d)
      await s.dire(1)
      await s.cliquer(s.page.getByRole("button", { name: t("commun.ajouter"), exact: true }))
      const dialogue = s.page.getByRole("dialog")
      await s.dire(2)
      await s.saisir(dialogue.locator("#exp-title"), d.ligne)
      await s.remplir(dialogue.locator("#exp-date"), "2026-10-02T10:30")
      await s.saisir(dialogue.locator("#exp-place"), d.lieu)
      await s.dire(3)
      await s.saisir(dialogue.locator("#exp-amount"), d.montant)
      await s.dire(4)
      await s.choisir(dialogue.locator("#exp-owner"), { index: 1 })
      await s.dire(5)
      await s.cliquer(dialogue.getByRole("button", { name: t("commun.enregistrer") }))
      await dialogue.waitFor({ state: "hidden" })
      await s.page.getByText(d.ligne).first().waitFor()
      await s.attendre(2500)
    },
  },
  "joindre-une-piece": {
    depart: "/projets",
    async jouer(s, t, d) {
      await ouvrirLeDossier(s, d, false)
      await s.dire(0)
      await s.dire(1)
      await s.cliquer(s.page.getByRole("button", { name: t("pieces.ligne.deposer_aria", { ligne: d.ligne }) }))
      const dialogue = s.page.getByRole("dialog")
      await s.dire(2)
      const fichier = dialogue.locator("#proof-file")
      await s.montrer(fichier)
      await fichier.setInputFiles({ name: d.fichierRecu, mimeType: "application/pdf", buffer: await recu(s.page, d.recu) })
      await s.attendre(800)
      await s.dire(3)
      await s.montrer(dialogue.locator("#proof-kind"))
      await s.cliquer(dialogue.getByRole("button", { name: t("pieces.deposer"), exact: true }))
      await dialogue.waitFor({ state: "hidden" })
      await s.page.getByText(d.fichierRecu).first().waitFor()
      await s.dire(4)
    },
  },
  "soumettre-un-dossier": {
    depart: "/projets",
    async jouer(s, t, d) {
      await ouvrirLeDossier(s, d, false)
      await s.dire(0)
      await s.dire(1)
      // « Soumettre » agit sans confirmation : le bouton disparaît quand le
      // dossier est soumis, et un refus du serveur le laisserait en place.
      const soumettre = s.page.getByRole("button", { name: t("depenses.circuit.soumettre"), exact: true })
      await s.cliquer(soumettre)
      await soumettre.waitFor({ state: "detached" })
      await s.dire(2)
      await s.dire(3)
    },
  },
  "importer-un-classeur": {
    depart: "/dossiers/import",
    async jouer(s, t, d) {
      await s.dire(0)
      await s.dire(1)
      const projet = s.page.locator("#import-project")
      const options = await projet.locator("option").allTextContents()
      const libelle = options.find((o) => o.includes(d.projet))
      if (!libelle) throw new Error(`Projet « ${d.projet} » absent de l'import.`)
      await s.choisir(projet, { label: libelle })
      // Le deuxième type du congrès (« Stands ») : le premier, D001, est soumis.
      await s.choisir(s.page.locator("#import-kind"), { index: 2 })
      await s.dire(2)
      const fichier = s.page.locator("#import-file")
      await s.montrer(fichier)
      await fichier.setInputFiles({
        name: d.fichierClasseur,
        mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        buffer: classeurDuGuide(d.lignesImportees),
      })
      await s.attendre(800)
      await s.dire(3)
      await s.cliquer(s.page.getByRole("button", { name: t("dossiers.import.simuler") }))
      await s.page.getByText(t("dossiers.import.resultat_simulation")).waitFor()
      await s.attendre(2000)
      await s.dire(4)
      await s.cliquer(s.page.getByRole("switch"))
      await s.cliquer(s.page.getByRole("button", { name: t("dossiers.import.importer"), exact: true }))
      await s.page.getByText(t("dossiers.import.resultat_import")).waitFor()
      await s.dire(5)
    },
  },
}

/** Un reçu d'exemple en PDF, imprimé par le navigateur : aucun fichier dans le dépôt. */
async function recu(page: Page, texte: string) {
  const feuille = await page.context().newPage()
  await feuille.setContent(
    `<div style="font-family: sans-serif; padding: 24px"><h2>JUSTI GH</h2><p>${texte}</p></div>`,
  )
  const pdf = await feuille.pdf({ format: "A6" })
  await feuille.close()
  return pdf
}

/** Le classeur du guide d'import, au format historique, aux noms de la démonstration. */
function classeurDuGuide(libelles: readonly string[]) {
  return classeur([
    ["N°ORDRE", "DATE", "TEAM", "OWNER", "LIBELLE DES TRANSACTIONS", "DEPENSES"],
    ...libelles.map((libelle, i) => [`G-${i + 1}`, `0${i + 1}/10/2026`, "Équipe Kara", "Kodjo Mensah", libelle, 150000 + i * 25000]),
  ])
}

/** Ouvre une session et fixe la langue du profil, hors caméra : la vidéo commence connectée. */
async function session(navigateur: Browser, langue: LangueDeGuide) {
  const contexte = await navigateur.newContext({ viewport: TAILLE, locale: langue })
  const page = await contexte.newPage()
  const erreurs: string[] = []
  page.on("console", (m) => {
    if (m.type() === "error" && !estLeRefusAttenduDuCode(m)) erreurs.push(m.text())
  })
  await signIn(page, BASE, credentials("COUNTRY"))
  const jeton = await page.evaluate(() => localStorage.getItem("justi_token"))
  const reponse = await page.request.patch(`${BASE}/api/me/`, {
    headers: { Authorization: `Token ${jeton}` },
    data: { language: langue },
  })
  if (!reponse.ok()) throw new Error(`La langue ${langue} n'a pas pu être fixée (${reponse.status()}).`)
  if (erreurs.length) throw new Error(`Erreurs de console à la connexion :\n${erreurs.join("\n")}`)
  const etat = await contexte.storageState()
  await contexte.close()
  return etat
}

/** Tourne un guide dans `brouillon` ; lève à la première erreur de console. */
async function tourner(
  navigateur: Browser,
  etat: Awaited<ReturnType<typeof session>>,
  langue: LangueDeGuide,
  id: IdDeGuide,
  t: T,
  brouillon: string,
) {
  const erreurs: string[] = []
  const contexte = await navigateur.newContext({
    viewport: TAILLE,
    locale: langue,
    storageState: etat,
    recordVideo: { dir: path.join(brouillon, "prises"), size: TAILLE },
  })
  await contexte.addInitScript({ content: POINTEUR })
  const page = await contexte.newPage()
  page.on("console", (m) => {
    if (m.type() === "error") erreurs.push(m.text())
  })
  page.on("pageerror", (e) => erreurs.push(String(e)))
  const scene = new Scene(page, LEGENDES[id][langue](t))
  try {
    await page.goto(`${BASE}${TOURNAGES[id].depart}`, { waitUntil: "networkidle" })
    await TOURNAGES[id].jouer(scene, t, DONNEES[langue])
    await page.screenshot({ path: path.join(brouillon, `${id}.jpg`), type: "jpeg", quality: 70 })
    await scene.attendre(1500)
  } finally {
    await contexte.close()
  }
  if (erreurs.length) throw new Error(`Erreurs de console pendant ${langue}/${id} :\n${erreurs.join("\n")}`)
  const fin = scene.maintenant()
  const video = page.video()
  if (!video) throw new Error(`Aucune vidéo pour ${id}.`)
  await reencoder(await video.path(), path.join(brouillon, `${id}.webm`))
  await writeFile(path.join(brouillon, `${id}.vtt`), sousTitres(scene.reperes, fin))
  console.log(`  ✓ ${langue}/${id} (${Math.round(fin / 1000)} s)`)
}

async function main() {
  const langue = langueDuTournage()
  const guides = guidesDuTournage()
  ffmpeg()
  const t = await dictionnaire(langue)
  // Les prises et les fichiers attendent dans un dossier temporaire : rien
  // n'arrive dans `public/` tant qu'un guide peut encore échouer.
  const brouillon = await mkdtemp(path.join(tmpdir(), "guides-"))
  const navigateur = await chromium.launch()
  try {
    console.log(`=== ${langue} ===`)
    const etat = await session(navigateur, langue)
    for (const id of guides) await tourner(navigateur, etat, langue, id, t, brouillon)
    await mkdir(path.join(SORTIE, langue), { recursive: true })
    for (const id of guides) {
      for (const extension of ["webm", "vtt", "jpg"]) {
        await copyFile(path.join(brouillon, `${id}.${extension}`), path.join(SORTIE, langue, `${id}.${extension}`))
      }
    }
    console.log(`→ ${path.join(SORTIE, langue)}`)
  } finally {
    await navigateur.close()
    await rm(brouillon, { recursive: true, force: true })
  }
}

await main()
