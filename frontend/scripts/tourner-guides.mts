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
 * toute erreur de console, et sur tout geste qui n'aboutit pas. Un réglage
 * faux (langue, `GUIDES_SEULS`, `GUIDES_FFMPEG`) l'arrête avant d'ouvrir le
 * navigateur, donc avant d'écrire dans la base (`guides/selection.ts`), de
 * même qu'un `SHOT_BASE` qui ne vise pas la machine locale, sauf
 * `GUIDES_CIBLE_JETABLE=oui` (`guides/cible.ts`). `GUIDES_OUT` écrit les
 * fichiers ailleurs que dans `public/guides/`, pour relire un tournage sans
 * toucher aux vidéos livrées.
 *
 * Chaque vidéo réencodée est enfin comparée, sous chaque sous-titre, à la
 * capture de la page prise au même moment (`guides/controle-images.ts`) :
 * une prise qui a perdu des images fait échouer le tournage, au lieu de
 * partir dans `public/guides/`.
 */
import { execFile } from "node:child_process"
import { existsSync, readdirSync } from "node:fs"
import { copyFile, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises"
import { homedir, tmpdir } from "node:os"
import path from "node:path"
import { promisify } from "node:util"
import { chromium, type Browser, type Locator, type Page } from "playwright"
import { type IdDeGuide, type LangueDeGuide } from "../src/lib/guides.ts"
import { exigerUneCibleJetable } from "./guides/cible.ts"
import { classeurDuGuide, dateDeSaisie, jourDuTournage, verifierLImport } from "./guides/classeur.ts"
import { controlerLesImages, pourcentage } from "./guides/controle-images.ts"
import { POINTEUR, Scene, espacesFines, sousTitres } from "./guides/scene.ts"
import {
  echecDuGeste,
  ffmpegInutilisable,
  guidesDuTournage,
  langueDuTournage,
  libelle,
  proposeLibvpx,
} from "./guides/selection.ts"
import { credentials, estLeRefusAttenduDuCode, signIn } from "./login.ts"

const BASE = process.env.SHOT_BASE ?? "http://localhost:5173"
const SORTIE = process.env.GUIDES_OUT ?? path.resolve(import.meta.dirname, "../public/guides")
const TAILLE = { width: 1280, height: 800 }

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

/**
 * Vérifie, avant le premier geste, que ce ffmpeg s'exécute et encode en VP8
 * (`libvpx`) : sinon l'échec ne survenait qu'au réencodage du premier
 * guide, quand la base jetable avait déjà reçu le projet du tournage.
 */
async function verifierFfmpeg() {
  const chemin = ffmpeg()
  const designe = Boolean(process.env.GUIDES_FFMPEG)
  const sortie = await promisify(execFile)(chemin, ["-hide_banner", "-encoders"]).then(
    ({ stdout }) => stdout,
    (erreur: unknown) => {
      throw ffmpegInutilisable(chemin, designe, erreur instanceof Error ? erreur.message : String(erreur))
    },
  )
  if (!proposeLibvpx(sortie)) throw ffmpegInutilisable(chemin, designe, "il ne propose pas l'encodeur libvpx (VP8)")
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
  return (cle: string, valeurs: Record<string, string> = {}) => libelle(brut, langue, cle, valeurs)
}

type T = Awaited<ReturnType<typeof dictionnaire>>

/**
 * Le jour du tournage : les dates du guide s'en déduisent.
 * `seed_demo` n'ouvre que les enveloppes de l'année en cours ; une date
 * écrite en dur faisait échouer la soumission filmée dès l'année suivante.
 */
const AUJOURDHUI = new Date()
const ANNEE = AUJOURDHUI.getFullYear()

/**
 * Les noms du référentiel de la démonstration (`seed_demo`, migration
 * `core.0016` pour les types de dossiers). Ce sont des données, pas des
 * libellés : l'écran les affiche tels quels dans les deux langues. Le
 * script les choisit par leur nom, jamais par leur position dans une
 * liste, qu'un nouvel élément du référentiel suffirait à décaler.
 */
const REFERENTIEL = {
  equipe: "Équipe Kara",
  responsable: "Kodjo Mensah",
  /** Le dossier qui reçoit le classeur : le D001 (« Collations ») est soumis par le guide précédent. */
  typeImporte: "Stands",
} as const

/** Ce que le manager saisit, dans la langue du guide. */
const DONNEES = {
  fr: {
    projet: `Congrès de cardiologie ${ANNEE}`,
    /** Le type d'origine, sous le libellé que le serveur sert en français (`core.0018`). */
    typeDeProjet: "Congrès",
    ligne: "Pause-café du congrès",
    lieu: "Lomé",
    montant: "85000",
    recu: "Reçu n° 0142 — Pause-café du congrès — 85 000 FCFA",
    fichierRecu: "recu-0142.pdf",
    fichierClasseur: "depenses-stands.xlsx",
    lignesImportees: ["Location du stand", "Impression des kakémonos", "Transport du matériel"],
  },
  en: {
    projet: `Cardiology congress ${ANNEE}`,
    typeDeProjet: "Congress",
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
      "Un projet regroupe les dépenses d'une opération : un congrès, un voyage…",
      `Cliquez sur « ${t("projets.liste.nouveau")} ».`,
      "Donnez-lui un nom que vos collègues reconnaîtront.",
      "Choisissez son type : il fixe les dossiers que le projet reçoit d'office.",
      "Choisissez l'équipe : chaque dossier du projet, et ses lignes, la porteront.",
      `Cliquez sur « ${t("commun.creer")} ».`,
      "Le projet est ouvert : il a sa référence et un dossier par type.",
    ],
    en: (t) => [
      "A project groups the expenses of one operation: a congress, a trip…",
      `Click “${t("projets.liste.nouveau")}”.`,
      "Give it a name your colleagues will recognise.",
      "Choose its type: it sets the dossiers the project receives automatically.",
      "Choose the team: every dossier of the project, and its lines, will carry it.",
      `Click “${t("commun.creer")}”.`,
      "The project is open: it has its reference and one dossier per type.",
    ],
  },
  "saisir-une-ligne": {
    fr: (t) => [
      "Ouvrez le dossier du bon type, dans un projet que vous avez ouvert.",
      `Cliquez sur « ${t("commun.ajouter")} » pour saisir une dépense.`,
      "Décrivez la dépense : ce qui a été payé, quand et où.",
      `Saisissez le montant ; payé dans une autre devise, ouvrez « ${t("depenses.formulaire.autre_devise")} ».`,
      "Équipe et manager responsable sont exigés pour soumettre : choisissez le manager.",
      `Cliquez sur « ${t("commun.enregistrer")} » : la ligne reste un brouillon que vous seul modifiez.`,
    ],
    en: (t) => [
      "Open the dossier of the right type, in a project you opened yourself.",
      `Click “${t("commun.ajouter")}” to enter an expense.`,
      "Describe the expense: what was paid, when and where.",
      `Enter the amount; if paid in another currency, open “${t("depenses.formulaire.autre_devise")}”.`,
      "A team and a responsible manager are required to submit: choose the manager.",
      `Click “${t("commun.enregistrer")}”: the line stays a draft that only you can edit.`,
    ],
  },
  "joindre-une-piece": {
    fr: (t) => [
      "Ouvrez le dossier : chaque ligne y reçoit sa pièce, le reçu ou la facture.",
      `Sur la ligne, cliquez sur « ${t("pieces.deposer")} ».`,
      "Choisissez le fichier : un PDF, une image ou un document.",
      `Choisissez le type de pièce, puis cliquez sur « ${t("pieces.deposer")} ».`,
      "La pièce est rangée sous sa ligne. Le siège la contrôlera.",
    ],
    en: (t) => [
      "Open the dossier: each line receives its document there, receipt or invoice.",
      `On the line, click “${t("pieces.deposer")}”.`,
      "Choose the file: a PDF, an image or a document.",
      `Choose the type of document, then click “${t("pieces.deposer")}”.`,
      "The document is filed under its line. Headquarters will review it.",
    ],
  },
  "soumettre-un-dossier": {
    fr: (t) => [
      "Ouvrez le dossier et relisez ses lignes : chacune doit avoir sa pièce.",
      `« ${t("depenses.circuit.soumettre")} » agit tout de suite, sans confirmation ni retour en arrière.`,
      "Vos lignes partent avec le dossier ; un brouillon d'un collègue bloque l'envoi.",
      `Cliquez sur « ${t("depenses.circuit.soumettre")} ».`,
      "Le dossier est soumis : ses lignes ne changent plus, seul le siège peut le rouvrir.",
      "Une ligne sans pièce part avec un avertissement ; le dossier attend ses pièces.",
    ],
    en: (t) => [
      "Open the dossier and check its lines: each one needs its document.",
      `“${t("depenses.circuit.soumettre")}” acts at once, with no confirmation and no way back.`,
      "Your lines go with the dossier; a colleague's draft line blocks the submission.",
      `Click “${t("depenses.circuit.soumettre")}”.`,
      "The dossier is submitted: its lines are fixed; only headquarters can reopen it.",
      "A line without a document goes with a warning; the dossier awaits its documents.",
    ],
  },
  "importer-un-classeur": {
    fr: (t) => [
      "Vos dépenses sont dans un classeur Excel ? Importez-les depuis la fiche du projet.",
      `Cliquez sur « ${t("dossiers.import.bouton")} », puis choisissez le dossier qui recevra les lignes.`,
      "Colonnes exigées : N°ORDRE, DATE, TEAM, OWNER, LIBELLE DES TRANSACTIONS, DEPENSES.",
      "TEAM doit être l'équipe du dossier, et le dossier votre brouillon.",
      "Simulez d'abord : rien n'est écrit, vous voyez ce qui serait créé.",
      `Sans erreur, désactivez la simulation, puis cliquez sur « ${t("dossiers.import.importer")} ».`,
      `Les lignes arrivent en brouillon : « ${t("dossiers.import.ouvrir_dossier")} » les montre.`,
      "Joignez la pièce de chaque ligne ; soumettez ensuite le dossier.",
    ],
    en: (t) => [
      "Are your expenses in an Excel workbook? Import them from the project page.",
      `Click “${t("dossiers.import.bouton")}”, then choose the dossier that will receive the lines.`,
      "Required columns: N°ORDRE, DATE, TEAM, OWNER, LIBELLE DES TRANSACTIONS, DEPENSES.",
      "TEAM must be the dossier's team, and the dossier your own draft.",
      "Simulate first: nothing is written, you see what would be created.",
      `With no error, turn the simulation off, then click “${t("dossiers.import.importer")}”.`,
      `The lines arrive as drafts: “${t("dossiers.import.ouvrir_dossier")}” shows them.`,
      "Upload each line's document; then submit the dossier.",
    ],
  },
}

interface Tournage {
  /** La page où commence la vidéo. */
  depart: string
  jouer: (s: Scene, t: T, d: Donnees) => Promise<void>
}

/**
 * Choisit dans une liste l'option qui porte ce libellé, et lève avec les
 * options présentes si elle n'y est pas : un choix par position prenait en
 * silence l'élément voisin.
 */
async function choisirParLibelle(s: Scene, liste: Locator, libelle: string, quoi: string) {
  const option = liste.locator("option").filter({ hasText: new RegExp(`^\\s*${echapperRegExp(libelle)}\\s*$`) })
  const trouvee = await option.first().waitFor({ state: "attached", timeout: 10_000 }).then(
    () => true,
    () => false,
  )
  if (!trouvee) {
    const presentes = (await liste.locator("option").allTextContents()).map((o) => `« ${o.trim()} »`)
    throw new Error(`${quoi} « ${libelle} » absent de la liste (options : ${presentes.join(", ")}).`)
  }
  await s.choisir(liste, { label: libelle })
}

function echapperRegExp(texte: string) {
  return texte.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

/**
 * Clique sur Simuler ou Importer et vérifie la réponse de l'API, pas
 * seulement l'écran : le titre de la carte de résultat s'affiche aussi
 * quand le classeur est refusé.
 */
async function importerEtVerifier(s: Scene, bouton: Locator, attendu: { lignes: number; simulation: boolean }) {
  const reponse = s.page.waitForResponse(
    (r) => r.request().method() === "POST" && new URL(r.url()).pathname === "/api/imports/expenses.xlsx",
  )
  // Si le clic échoue, cette attente rejette à la fermeture de la page :
  // sans gestionnaire, ce rejet tardif masquerait la vraie cause.
  reponse.catch(() => undefined)
  await s.cliquer(bouton)
  const recue = await reponse
  const corps = (await recue.json().catch(() => ({}))) as Parameters<typeof verifierLImport>[2]
  verifierLImport(attendu.simulation ? "La simulation de l'import" : "L'import", recue.status(), corps, attendu)
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
      // Le type est une donnée du serveur (décision 119), sous son libellé.
      await choisirParLibelle(s, dialogue.locator("#projet-kind"), d.typeDeProjet, "Le type de projet")
      await s.dire(4)
      await choisirParLibelle(s, dialogue.locator("#projet-team"), REFERENTIEL.equipe, "L'équipe")
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
      await s.remplir(dialogue.locator("#exp-date"), dateDeSaisie(jourDuTournage(AUJOURDHUI, 3)))
      await s.saisir(dialogue.locator("#exp-place"), d.lieu)
      await s.dire(3)
      await s.saisir(dialogue.locator("#exp-amount"), d.montant)
      // Le panneau de la devise étrangère se montre, ouvert puis refermé :
      // la dépense filmée est payée dans la devise du pays.
      const autreDevise = dialogue.getByText(t("depenses.formulaire.autre_devise"), { exact: true })
      await s.cliquer(autreDevise)
      await s.attendre(1200)
      await s.cliquer(autreDevise)
      await s.dire(4)
      await choisirParLibelle(s, dialogue.locator("#exp-owner"), REFERENTIEL.responsable, "Le manager responsable")
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
      await s.dire(0)
      await ouvrirLeDossier(s, d)
      await s.dire(1)
      await s.cliquer(s.page.getByRole("button", { name: t("pieces.ligne.deposer_aria", { ligne: d.ligne }) }))
      const dialogue = s.page.getByRole("dialog")
      await s.dire(2)
      const fichier = dialogue.locator("#proof-file")
      await s.montrer(fichier)
      await fichier.setInputFiles({ name: d.fichierRecu, mimeType: "application/pdf", buffer: await recu(s.page, d.recu) })
      await s.attendre(800)
      await s.dire(3)
      await choisirParLibelle(s, dialogue.locator("#proof-kind"), t("libelles.piece_type.receipt"), "Le type de pièce")
      await s.cliquer(dialogue.getByRole("button", { name: t("pieces.deposer"), exact: true }))
      await dialogue.waitFor({ state: "hidden" })
      await s.page.getByText(d.fichierRecu).first().waitFor()
      await s.dire(4)
    },
  },
  "soumettre-un-dossier": {
    depart: "/projets",
    async jouer(s, t, d) {
      await s.dire(0)
      await ouvrirLeDossier(s, d)
      // « Soumettre » agit sans confirmation : le bouton disparaît quand le
      // dossier est soumis, et un refus du serveur le laisserait en place.
      const soumettre = s.page.getByRole("button", { name: t("depenses.circuit.soumettre"), exact: true })
      await s.montrer(soumettre)
      await s.dire(1)
      await s.dire(2)
      await s.relacher()
      await s.dire(3)
      await s.cliquer(soumettre)
      await soumettre.waitFor({ state: "detached" })
      await s.dire(4)
      await s.dire(5)
    },
  },
  "importer-un-classeur": {
    depart: "/projets",
    async jouer(s, t, d) {
      await s.dire(0)
      await s.cliquer(s.page.getByRole("link", { name: d.projet }).first())
      await s.page.waitForLoadState("networkidle")
      await s.dire(1)
      // Le bouton de la fiche projet ouvre l'import, ce projet déjà choisi.
      await s.cliquer(s.page.getByRole("button", { name: t("dossiers.import.bouton"), exact: true }))
      await s.page.waitForURL(/\/dossiers\/import/)
      await s.page.waitForLoadState("networkidle")
      await choisirParLibelle(s, s.page.locator("#import-kind"), REFERENTIEL.typeImporte, "Le type de dossier")
      await s.dire(2)
      const fichier = s.page.locator("#import-file")
      await s.montrer(fichier)
      await fichier.setInputFiles({
        name: d.fichierClasseur,
        mimeType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        buffer: classeurDuGuide(d.lignesImportees, {
          aujourdhui: AUJOURDHUI,
          equipe: REFERENTIEL.equipe,
          responsable: REFERENTIEL.responsable,
        }),
      })
      await s.attendre(800)
      await s.dire(3)
      await s.dire(4)
      const attendues = d.lignesImportees.length
      await importerEtVerifier(s, s.page.getByRole("button", { name: t("dossiers.import.simuler") }), {
        lignes: attendues,
        simulation: true,
      })
      await s.page.getByText(t("dossiers.import.resultat_simulation")).waitFor()
      await s.attendre(2000)
      await s.dire(5)
      await s.cliquer(s.page.getByRole("switch"))
      await importerEtVerifier(s, s.page.getByRole("button", { name: t("dossiers.import.importer"), exact: true }), {
        lignes: attendues,
        simulation: false,
      })
      await s.page.getByText(t("dossiers.import.resultat_import")).waitFor()
      await s.dire(6)
      await s.cliquer(s.page.getByRole("button", { name: t("dossiers.import.ouvrir_dossier") }))
      await s.page.waitForURL(/\/dossiers\/\d+$/)
      await s.page.getByText(d.lignesImportees[0]).first().waitFor()
      await s.dire(7)
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

/** Ouvre une session et fixe la langue du profil, hors caméra : la vidéo commence connectée. */
async function session(navigateur: Browser, langue: LangueDeGuide) {
  const contexte = await navigateur.newContext({ viewport: TAILLE, locale: langue })
  const page = await contexte.newPage()
  const erreurs: string[] = []
  page.on("console", (m) => {
    if (m.type() === "error" && !estLeRefusAttenduDuCode(m)) erreurs.push(m.text())
  })
  try {
    await signIn(page, BASE, credentials("COUNTRY"))
    const jeton = await page.evaluate(() => localStorage.getItem("justi_token"))
    const reponse = await page.request.patch(`${BASE}/api/me/`, {
      headers: { Authorization: `Token ${jeton}` },
      data: { language: langue },
    })
    if (!reponse.ok()) throw new Error(`La langue ${langue} n'a pas pu être fixée (${reponse.status()}).`)
  } catch (cause) {
    throw echecDuGeste(`la connexion (${langue})`, cause, erreurs)
  }
  if (erreurs.length) throw new Error(`Erreurs de console à la connexion :\n${erreurs.join("\n")}`)
  const etat = await contexte.storageState()
  await contexte.close()
  return etat
}

/**
 * Tourne un guide dans `brouillon`. Lève si un geste échoue — avec les
 * erreurs de console déjà collectées, qui disent souvent pourquoi — ou, le
 * tournage fini, s'il y a eu la moindre erreur de console.
 */
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
  // Le français reçoit ses espaces fines insécables (« : », « ? », « »).
  const legendes = LEGENDES[id][langue](t).map((texte) => (langue === "fr" ? espacesFines(texte) : texte))
  const scene = new Scene(page, legendes)
  try {
    await page.goto(`${BASE}${TOURNAGES[id].depart}`, { waitUntil: "networkidle" })
    await TOURNAGES[id].jouer(scene, t, DONNEES[langue])
    await page.screenshot({ path: path.join(brouillon, `${id}.jpg`), type: "jpeg", quality: 70 })
    await scene.attendre(1500)
  } catch (cause) {
    throw echecDuGeste(`${langue}/${id}`, cause, erreurs)
  } finally {
    await contexte.close()
  }
  if (erreurs.length) throw new Error(`Erreurs de console pendant ${langue}/${id} :\n${erreurs.join("\n")}`)
  const fin = scene.maintenant()
  const video = page.video()
  if (!video) throw new Error(`Aucune vidéo pour ${id}.`)
  const webm = path.join(brouillon, `${id}.webm`)
  await reencoder(await video.path(), webm)
  // La vidéo telle qu'elle sera servie, contre ce que la page montrait :
  // lève si l'enregistrement a perdu des images sous un sous-titre.
  const ecarts = await controlerLesImages({
    navigateur,
    ffmpeg: ffmpeg(),
    video: webm,
    reperes: scene.reperes,
    captures: scene.captures,
    guide: `${langue}/${id}`,
  })
  await writeFile(path.join(brouillon, `${id}.vtt`), sousTitres(scene.reperes, fin))
  const pire = Math.max(0, ...ecarts.map((e) => e.ecart))
  console.log(`  ✓ ${langue}/${id} (${Math.round(fin / 1000)} s, écart d'image au plus ${pourcentage(pire)})`)
}

async function main() {
  // Avant tout geste : le tournage écrit pour de bon dans la base visée,
  // il n'en vise donc qu'une jetable.
  exigerUneCibleJetable(BASE, process.env.GUIDES_CIBLE_JETABLE)
  const langue = langueDuTournage(process.env.GUIDES_LANGUE)
  const guides = guidesDuTournage(process.env.GUIDES_SEULS)
  await verifierFfmpeg()
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
