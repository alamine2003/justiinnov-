/**
 * Revue visuelle : parcourt l'application et capture les écrans principaux.
 *
 * Les identifiants ne sont jamais codés en dur — ils viennent de
 * l'environnement :
 *
 *   SHOT_HQ_USER=admin.innov SHOT_HQ_PASSWORD=… SHOT_HQ_TOTP_SECRET=… \
 *   SHOT_COUNTRY_USER=togo.innov SHOT_COUNTRY_PASSWORD=… SHOT_COUNTRY_TOTP_SECRET=… \
 *   npx tsx scripts/screenshot.ts
 *
 * Le script échoue (code de sortie 1) sur toute erreur de console et sur
 * toute attente non tenue : un compte qui verrait des lignes hors de son
 * périmètre, une redirection absente, un titre qui manque.
 */
import { chromium, type Browser, type Page } from "playwright"
import { credentials, estLeRefusAttenduDuCode, signIn } from "./login.ts"

const BASE = process.env.SHOT_BASE ?? "http://localhost:5173"
const OUT = process.env.SHOT_OUT ?? "/tmp"
/**
 * `SHOT_EXPECT_DATA=0` : la pile est vide (pas de dossier, pas d'entrée de
 * journal) ; les attentes sur la présence de données sont alors consignées
 * sans faire échouer le script. Les attentes sur les droits et la navigation
 * restent exigées.
 */
const EXPECT_DATA = process.env.SHOT_EXPECT_DATA !== "0"

const errors: string[] = []
const failures: string[] = []

/** Attente vérifiée : consignée, elle fait échouer le script sans l'arrêter. */
function expect(condition: boolean, message: string) {
  if (condition) {
    console.log(`  ✓ ${message}`)
  } else {
    console.log(`  ✗ ${message}`)
    failures.push(message)
  }
}

/** Attente sur la présence de données : facultative quand la pile est vide. */
function expectData(condition: boolean, message: string) {
  if (!EXPECT_DATA && !condition) {
    console.log(`  – ${message} (pile sans données, SHOT_EXPECT_DATA=0)`)
    return
  }
  expect(condition, message)
}

async function newPage(browser: Browser, viewport = { width: 1440, height: 900 }) {
  // Le navigateur de Playwright se présente en anglais ; l'interface suivrait
  // cette langue et les attentes ci-dessous, écrites en français, échoueraient.
  const page = await browser.newPage({ viewport, locale: "fr-FR" })
  page.on("console", (m) => {
    if (m.type() === "error" && !estLeRefusAttenduDuCode(m)) errors.push(`[console] ${m.text()}`)
  })
  page.on("pageerror", (e) => errors.push(`[pageerror] ${String(e)}`))
  return page
}

async function login(page: Page, prefix: string) {
  const account = credentials(prefix)
  await signIn(page, BASE, account)
  await page.waitForTimeout(1500)
  // Les attentes ci-dessous sont écrites en français ; la préférence du
  // profil l'emporte sur celle du navigateur, elle est donc fixée d'abord.
  await setLanguage(page, "fr")
  return account.user
}

/** Enregistre la langue sur le profil (`PATCH /api/me/`), avec le jeton de la session ouverte. */
async function setLanguage(page: Page, language: "fr" | "en") {
  const token = await page.evaluate(() => localStorage.getItem("justi_token"))
  if (!token) return
  const response = await page.request.patch(`${BASE}/api/me/`, {
    headers: { Authorization: `Token ${token}` },
    data: { language },
  })
  if (!response.ok()) {
    console.log(`  – la langue n'a pas pu être fixée (${response.status()})`)
    return
  }
  await page.reload({ waitUntil: "networkidle" })
  await page.waitForTimeout(800)
}

/** Le déploiement annonce-t-il la supervision (`GET /api/me/` → `supervision`) ? */
async function supervisionAnnoncee(page: Page): Promise<boolean> {
  const token = await page.evaluate(() => localStorage.getItem("justi_token"))
  if (!token) return false
  const response = await page.request.get(`${BASE}/api/me/`, {
    headers: { Authorization: `Token ${token}` },
  })
  if (!response.ok()) return false
  const me = (await response.json()) as { supervision?: boolean }
  return me.supervision === true
}

async function shot(page: Page, name: string) {
  await page.screenshot({ path: `${OUT}/shot_${name}.png`, fullPage: false })
}

async function goto(page: Page, path: string, settle = 1000) {
  await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" })
  await page.waitForTimeout(settle)
}

async function main() {
  const browser = await chromium.launch()

  // --- Parcours siège : accès à tous les pays et à toutes les pages --------
  const hq = await newPage(browser)
  const hqUser = await login(hq, "HQ")
  console.log(`\n=== SIÈGE (${hqUser}) ===`)
  const hqNav = await hq.getByRole("navigation", { name: "Navigation principale" }).getByRole("link").allTextContents()
  expect(hqNav.some((t) => t.includes("Configuration")), "le siège voit « Configuration »")
  expect(hqNav.some((t) => t.includes("Audit")), "le siège voit « Audit »")
  // Les guides vidéo montrent les gestes du pays : le siège n'en a aucun.
  expect(!hqNav.some((t) => t.includes("Guide vidéo")), "le siège ne voit pas « Guide vidéo »")
  expect((await hq.textContent("h1"))?.includes("Pilotage") ?? false, "le tableau de bord s'ouvre")
  // Le menu du compte : la supervision (Grafana) aux administrateurs, dans
  // un nouvel onglet ; la pastille 2FA pour un compte enrôlé (ceux de la CI
  // le sont).
  await hq.getByRole("button", { name: "Menu du compte" }).click()
  // Le menu s'ouvre avec une transition : compter ses entrées ou le
  // photographier avant la fin donnerait un menu vide ou translucide.
  await hq.getByRole("menu").waitFor({ state: "visible" })
  await hq.waitForTimeout(400)
  // « Supervision » n'est pas un droit mais un réglage de déploiement
  // (me.supervision) : la pile de la CI n'embarque pas Grafana.
  const supervisionActive = await supervisionAnnoncee(hq)
  const supervision = hq.getByRole("menuitem", { name: "Supervision" })
  expect(
    (await supervision.count()) === (supervisionActive ? 1 : 0),
    supervisionActive
      ? "le siège voit « Supervision » dans le menu du compte"
      : "sans Grafana déployé, « Supervision » n'apparaît pas",
  )
  if (supervisionActive) {
    expect(
      (await supervision.getAttribute("href")) === "/grafana/" &&
        (await supervision.getAttribute("target")) === "_blank" &&
        (await supervision.getAttribute("rel")) === "noopener noreferrer",
      "« Supervision » ouvre /grafana/ dans un nouvel onglet",
    )
  }
  expect(
    ((await hq.getByRole("menu").textContent()) ?? "").includes("2FA active"),
    "le menu du compte montre la pastille « 2FA active » d'un compte enrôlé",
  )
  await shot(hq, "menu_compte")
  await hq.keyboard.press("Escape")
  // Sans pays choisi, la consolidation ne propose pas de répartition : deux
  // équipes homonymes de pays différents fusionneraient. Le siège doit
  // d'abord choisir un pays.
  expect(
    ((await hq.textContent("main")) ?? "").includes("Choisissez un pays"),
    "la consolidation invite à choisir un pays pour la répartition",
  )
  await shot(hq, "pilotage")
  await hq.getByLabel("Pays").selectOption({ index: 1 })
  await hq.waitForTimeout(1200)
  // L'analyse d'un pays tient en un panneau : Mois, Répartition, Pays ; la
  // répartition se lit un axe à la fois, choisi dans une liste (DESIGN.md,
  // « Hauteur d'écran »).
  expect((await hq.getByRole("tab").count()) === 3, "l'analyse d'un pays propose ses trois onglets")
  await shot(hq, "pilotage_pays")
  await hq.getByRole("tab", { name: "Répartition" }).click()
  const axe = hq.getByRole("combobox", { name: "Répartir par" })
  expect((await axe.locator("option").count()) === 8, "la répartition propose ses huit axes")
  await axe.selectOption("by_project")
  await shot(hq, "pilotage_repartition")

  // Le sélecteur de langue est un groupe radio, comme celui du thème.
  await hq.getByRole("button", { name: "Langue de l'interface" }).click()
  const menuLangue = hq.getByRole("menu")
  await menuLangue.waitFor({ state: "visible" })
  await hq.waitForTimeout(300)
  expect(
    (await hq.getByRole("menuitemradio", { name: "English" }).count()) === 1,
    "le sélecteur de langue propose l'anglais",
  )
  await hq.getByRole("menuitemradio", { name: "English" }).click()
  await menuLangue.waitFor({ state: "hidden" })
  await hq.waitForTimeout(1200)
  const navAnglaise = await hq.getByRole("navigation", { name: "Main navigation" }).getByRole("link").allTextContents()
  expect(navAnglaise.some((t) => t.includes("Settings")), "l'interface passe en anglais")
  expect((await hq.getAttribute("html", "lang")) === "en", "<html lang> suit la langue")
  await shot(hq, "pilotage_en")
  await hq.getByRole("button", { name: "Interface language" }).click()
  await menuLangue.waitFor({ state: "visible" })
  await hq.waitForTimeout(300)
  await hq.getByRole("menuitemradio", { name: "Français" }).click()
  await menuLangue.waitFor({ state: "hidden" })
  await hq.waitForTimeout(1200)
  expect((await hq.getAttribute("html", "lang")) === "fr", "le retour au français est appliqué")

  await hq.getByRole("button", { name: /^Notifications/ }).click()
  await hq.waitForTimeout(900)
  expect(
    ((await hq.textContent("[data-slot=sheet-title]")) ?? "").includes("Notifications"),
    "le panneau de notifications s'ouvre",
  )
  await shot(hq, "notifications")
  await hq.keyboard.press("Escape")
  await hq.waitForTimeout(400)

  // Version 2.0 (décision 100) : « Projets » est la rubrique principale.
  expect(hqNav.some((t) => t.includes("Projets")), "la navigation porte « Projets »")
  expect(!hqNav.some((t) => t.includes("Dossiers")), "« Dossiers » a quitté la navigation")
  await goto(hq, "/projets", 1200)
  expect((await hq.textContent("h1"))?.includes("Projets") ?? false, "la page Projets s'ouvre")
  await shot(hq, "projets")
  // Le congrès togolais du jeu de démonstration, s'il est là : il a des
  // dossiers remplis et un historique ; à défaut, le premier projet.
  const congresDemo = hq.getByRole("link", { name: "Lancement gamme pédiatrique" })
  const premierProjet = (await congresDemo.count())
    ? congresDemo.first()
    : hq.locator("tbody tr").getByRole("link").first()
  if (await premierProjet.count()) {
    await premierProjet.click()
    await hq.waitForURL("**/projets/*", { timeout: 15000 })
    await hq.waitForTimeout(1200)
    // Décision 106 : un projet naît avec ses dossiers, personne n'en ouvre.
    expect(
      (await hq.getByRole("button", { name: /Nouveau dossier/ }).count()) === 0,
      "aucun dossier ne s'ouvre à la main dans un projet",
    )
    // Décision 108 : le siège modifie, motif à l'appui ; il ne renomme pas.
    expect(
      (await hq.getByRole("button", { name: "Modifier" }).count()) === 1 &&
        (await hq.getByRole("button", { name: "Renommer" }).count()) === 0,
      "le siège modifie le projet sans le renommer",
    )
    await shot(hq, "projet_detail")
    await hq.getByRole("tab", { name: "Historique" }).click()
    await hq.waitForTimeout(1200)
    expectData((await hq.locator("ol li").count()) > 0, "l'historique du projet a des entrées")
    await shot(hq, "projet_historique")
  }

  await goto(hq, "/dossiers")
  const hqDossiers = await hq.locator("tbody tr").count()
  expectData(hqDossiers > 0, `des dossiers sont listés (${hqDossiers})`)
  // Décision 89 : le siège contrôle, il ne déclare pas.
  expect(
    (await hq.getByRole("link", { name: /Nouveau dossier/ }).count()) +
      (await hq.getByRole("button", { name: /Nouveau dossier/ }).count()) === 0,
    "le siège n'a pas de bouton « Nouveau dossier »",
  )
  expect(
    (await hq.getByRole("link", { name: /^Importer$/ }).count()) +
      (await hq.getByRole("button", { name: /^Importer$/ }).count()) === 0,
    "le siège n'a pas de bouton « Importer »",
  )
  await shot(hq, "dossiers")

  // Un dossier aux lignes justifiées par leur pièce (décision 107) : celui
  // des stands du jeu de démonstration, à défaut le premier.
  const standsDemo = hq.locator("tbody tr", { hasText: "Stands — lancement" }).getByRole("link")
  const firstDossier = (await standsDemo.count())
    ? standsDemo.first()
    : hq.locator("tbody tr").getByRole("link").first()
  if (await firstDossier.count()) {
    await firstDossier.click()
    await hq.waitForURL("**/dossiers/*", { timeout: 15000 })
    await hq.waitForTimeout(1200)
    expect(Boolean(await hq.textContent("h1")), "la fiche du dossier porte son N°ORDRE")
    expectData(
      (await hq.getByText("Justificatif", { exact: true }).count()) > 0,
      "une ligne porte son justificatif",
    )
    await shot(hq, "dossier_detail")

    // Un dialogue : la justification ou, à défaut, le dépôt de pièce.
    const dialogueBouton = hq.getByRole("button", { name: /Marquer justifié|Déposer|Ajouter/ }).first()
    if (await dialogueBouton.count()) {
      await dialogueBouton.click()
      await hq.waitForTimeout(600)
      expect((await hq.getByRole("dialog").count()) > 0, "un dialogue s'ouvre sur la fiche")
      await shot(hq, "dossier_dialogue")
      await hq.keyboard.press("Escape")
      await hq.waitForTimeout(400)
    }

    // L'aperçu d'une pièce, s'il en existe une prévisualisable.
    const apercu = hq.getByRole("button", { name: /^Prévisualiser/ }).first()
    if (await apercu.count()) {
      await apercu.click()
      await hq.waitForTimeout(1500)
      expect((await hq.getByRole("dialog").count()) > 0, "l'aperçu d'une pièce s'ouvre")
      await shot(hq, "dossier_apercu")
      await hq.keyboard.press("Escape")
      await hq.waitForTimeout(400)
    } else {
      console.log("  – aucune pièce prévisualisable sur ce dossier")
    }
  }

  await goto(hq, "/registre", 1200)
  expectData((await hq.locator("tbody tr").count()) > 0, "le registre a des lignes")
  expect(
    (await hq.getByRole("button", { name: "Exporter" }).count()) === 1,
    "le registre propose le menu « Exporter » au siège",
  )
  await shot(hq, "registre")

  // Décision 111 : l'audit en tableau de bord, puis ses deux journaux.
  await goto(hq, "/audit", 1500)
  expect(
    (await hq.getByText("Dossiers soumis").count()) > 0,
    "la vue d'ensemble de l'audit compte les dossiers soumis",
  )
  await shot(hq, "audit_vue_ensemble")
  await hq.getByRole("tab", { name: "Circuit" }).click()
  await hq.waitForTimeout(1200)
  expectData((await hq.locator("tbody tr").count()) > 0, "le journal du circuit a des entrées")
  await shot(hq, "audit_circuit")
  await hq.getByRole("tab", { name: "Référentiel et comptes" }).click()
  await hq.waitForTimeout(1200)
  expectData((await hq.locator("tbody tr").count()) > 0, "l'historique du référentiel a des entrées")
  await shot(hq, "audit_referentiel")

  // Décision 120 : la corbeille se lit au siège, avec l'état de l'interrupteur.
  await goto(hq, "/corbeille", 1200)
  expect(
    (await hq.getByRole("heading", { name: "Corbeille" }).count()) === 1,
    "la page Corbeille s'ouvre au siège",
  )
  expect(
    (await hq.getByText(/Les suppressions sont (ouvertes|fermées)/).count()) === 1,
    "la corbeille dit si les suppressions sont ouvertes",
  )
  await shot(hq, "corbeille")

  await goto(hq, "/countries")
  const hqCountries = await hq.locator("tbody tr").count()
  expectData(hqCountries > 1, `le siège voit plusieurs pays (${hqCountries})`)
  await shot(hq, "countries_hq")

  await goto(hq, "/budgets", 1200)
  expect((await hq.textContent("h1"))?.includes("Budgets") ?? false, "la page Budgets s'ouvre")
  await shot(hq, "budgets_pays")

  // La page n'a plus d'onglets : tous les pays se comparent en barres, et un
  // pays choisi ouvre son enveloppe en rail avec ses sous-enveloppes. Un
  // compte qui n'a qu'un pays n'a pas de sélecteur : le sien s'ouvre seul.
  const choixPays = hq.getByLabel("Pays")
  if ((await choixPays.count()) === 1) {
    await choixPays.selectOption({ index: 1 })
    await hq.waitForTimeout(900)
  }
  expect(
    (await hq.getByRole("heading", { name: /enveloppe du pays/ }).count()) === 1,
    "l'enveloppe d'un pays s'ouvre en rail",
  )
  // Décision 91 : le compte du siège est l'administrateur, qui lit les
  // enveloppes sans les attribuer, les modifier ni les supprimer.
  expect(
    (await hq.getByRole("button", { name: /Attribuer|Découper encore|Supprimer l'enveloppe|Modifier l'enveloppe|Modifier la sous-enveloppe/ }).count()) === 0,
    "l'administrateur lit les enveloppes sans les attribuer, modifier ni supprimer",
  )
  await shot(hq, "budgets_enveloppes")

  // Les réallocations sont sur la même page, en flux, sous les enveloppes.
  const reallocations = hq.getByRole("heading", { name: "Réallocations" })
  expect((await reallocations.count()) === 1, "les réallocations suivent sur la même page")
  await reallocations.scrollIntoViewIfNeeded()
  await hq.waitForTimeout(400)
  await shot(hq, "budgets_reallocations")

  await goto(hq, "/configuration", 1200)
  const onglets = await hq.getByRole("tab").allTextContents()
  expect(onglets.includes("Permissions"), "la configuration propose l'onglet Permissions")
  await shot(hq, "configuration_general")

  for (const [onglet, nom] of [
    ["Utilisateurs", "configuration_utilisateurs"],
    ["Pays", "configuration_pays"],
    ["Types de projets", "configuration_types_projets"],
    ["Permissions", "configuration_permissions"],
  ] as const) {
    await hq.getByRole("tab", { name: onglet }).click()
    await hq.waitForTimeout(900)
    expectData((await hq.locator("tbody tr").count()) > 0, `Configuration › ${onglet} a des lignes`)
    if (onglet === "Types de projets") {
      // Décisions 108 et 119 : les deux listes sont au super administrateur
      // seul ; le compte de capture du siège est administrateur (RH), il
      // les lit, chaque type de projet avec ses types de dossiers.
      expect(
        (await hq.getByRole("button", { name: /Ajouter un type/ }).count()) === 0,
        "la RH lit les types de projets et de dossiers sans pouvoir les modifier",
      )
      for (const type of ["Congrès", "Voyage", "Soutien financier"]) {
        expectData(
          (await hq.getByRole("heading", { name: type, exact: true }).count()) === 1,
          `Configuration › Types de projets montre « ${type} »`,
        )
      }
    }
    await shot(hq, nom)
  }

  // --- Hauteur d'écran : dès lg, la page ne défile pas ---------------------
  // Son tableau ou son détail défile dans sa boîte (DESIGN.md, « Hauteur
  // d'écran »). Le défilement nul n'était mesuré qu'à la main : une ligne
  // « Retour » oubliée faisait défiler les fiches de 44 px.
  await goto(hq, "/projets")
  const fiche = await hq.evaluate(() =>
    [...document.querySelectorAll("main a")].map((a) => a.getAttribute("href")).find((h) => h && /^\/projets\/\d+$/.test(h)),
  )
  await goto(hq, "/dossiers")
  const ficheDossier = await hq.evaluate(() =>
    [...document.querySelectorAll("main a")].map((a) => a.getAttribute("href")).find((h) => h && /^\/dossiers\/\d+$/.test(h)),
  )
  const ecrans = [
    "/", "/projets", "/dossiers", "/registre", "/audit", "/corbeille", "/budgets", "/configuration", "/countries",
  ]
  if (fiche) ecrans.push(fiche)
  if (ficheDossier) ecrans.push(ficheDossier)
  // 1 366 × 657 : un portable 1 366 × 768, barre du navigateur déduite.
  for (const [largeur, hauteur] of [[1366, 768], [1366, 657], [1024, 768], [1920, 1080]]) {
    await hq.setViewportSize({ width: largeur, height: hauteur })
    const defilent: string[] = []
    for (const chemin of ecrans) {
      await goto(hq, chemin, 600)
      const exces = await hq.evaluate(() => document.documentElement.scrollHeight - window.innerHeight)
      if (exces > 0) defilent.push(`${chemin} (${exces} px)`)
    }
    expect(defilent.length === 0, `à ${largeur} × ${hauteur}, aucune page ne défile${defilent.length ? ` — ${defilent.join(", ")}` : ""}`)
  }
  // Fenêtre trop basse pour tout tenir : la page défile, et la pagination
  // reste atteignable — la carte ne la rogne pas.
  await hq.setViewportSize({ width: 1280, height: 560 })
  await goto(hq, "/registre", 800)
  await hq.evaluate(() => {
    // `scroll-smooth` sur <html> : sans cela, la mesure suivrait un défilement en cours.
    document.documentElement.style.scrollBehavior = "auto"
    window.scrollTo(0, document.documentElement.scrollHeight)
  })
  const paginationAtteinte = await hq.evaluate(() => {
    const pagination = document.querySelector("main [data-slot=pagination]")
    if (!pagination) return false
    const r = pagination.getBoundingClientRect()
    const vu = document.elementFromPoint(r.left + 4, r.top + r.height / 2)
    return r.bottom <= window.innerHeight && vu !== null && pagination.contains(vu)
  })
  expect(paginationAtteinte, "à 1280 × 560, la pagination du registre reste visible")
  await hq.setViewportSize({ width: 1440, height: 900 })

  // --- Parcours pays : périmètre restreint --------------------------------
  const rep = await newPage(browser)
  const repUser = await login(rep, "COUNTRY")
  console.log(`\n=== MANAGER DE PAYS (${repUser}) ===`)
  const perimetre = (await rep.getByRole("banner").textContent()) ?? ""
  expect(!perimetre.includes("Siège"), "le périmètre affiché est celui d'un pays, pas le siège")
  const repNav = await rep.getByRole("navigation", { name: "Navigation principale" }).getByRole("link").allTextContents()
  expect(!repNav.some((t) => t.includes("Configuration")), "le pays ne voit pas « Configuration »")
  expect(!repNav.some((t) => t.includes("Audit")), "le pays ne voit pas « Audit »")
  await rep.getByRole("button", { name: "Menu du compte" }).click()
  await rep.getByRole("menu").waitFor({ state: "visible" })
  await rep.waitForTimeout(400)
  expect(
    (await rep.getByRole("menuitem", { name: "Déconnexion" }).count()) === 1 &&
      (await rep.getByRole("menuitem", { name: "Supervision" }).count()) === 0,
    "le pays ne voit pas « Supervision »",
  )
  await rep.keyboard.press("Escape")
  // Le guide vidéo (décision 118) : le pays voit la page et son sommaire
  // des cinq gestes du manager ; seul le guide ouvert par défaut (le
  // premier, en français, la langue des captures) est vérifié ici — sa
  // vidéo, ses sous-titres et son affiche répondent 200 avec leur type. Les
  // 30 fichiers (5 guides × 2 langues × 3) sont tenus sur disque par
  // `src/lib/guides-fichiers.test.ts`.
  expect(repNav.some((t) => t.includes("Guide vidéo")), "le pays voit « Guide vidéo »")
  await goto(rep, "/guide", 1200)
  await shot(rep, "guide_video")
  // Le sommaire est fait de liens `?video=` (2.2) : un guide s'ouvre aussi
  // dans un nouvel onglet.
  const sommaire = rep.getByRole("navigation", { name: "Les guides" }).getByRole("link")
  expect((await sommaire.count()) === 5, "le guide propose les cinq gestes du manager")
  expect(
    (await sommaire.nth(4).getAttribute("href"))?.endsWith("?video=importer-un-classeur") === true,
    "chaque guide du sommaire a son adresse",
  )
  // Le type compte autant que le statut : le serveur de développement
  // répond 200 avec index.html pour un fichier absent.
  for (const [selecteur, attribut, type] of [
    ["video source", "src", "video/webm"],
    ["video track", "src", "text/vtt"],
    ["video", "poster", "image/jpeg"],
  ] as const) {
    const adresse = await rep.locator(selecteur).first().getAttribute(attribut)
    const reponse = adresse ? await rep.request.get(`${BASE}${adresse}`) : null
    expect(
      reponse?.status() === 200 && (reponse.headers()["content-type"] ?? "").startsWith(type),
      `le guide ouvert sert ${adresse} en ${type}`,
    )
  }
  await goto(rep, "/projets", 1200)
  await shot(rep, "projets_representant")
  // Le pays crée ses projets : le type choisi annonce les dossiers qu'il
  // recevra (décision 106). Le dialogue s'ouvre sans être soumis — la base
  // de capture est partagée par les trois scripts.
  const nouveauProjet = rep.getByRole("button", { name: "Nouveau projet" })
  expect((await nouveauProjet.count()) === 1, "le pays peut créer un projet")
  if (await nouveauProjet.count()) {
    await nouveauProjet.click()
    await rep.waitForTimeout(800)
    await rep.getByLabel("Type de projet").selectOption("congres")
    await rep.waitForTimeout(800)
    expect(
      (await rep.getByText(/Le projet recevra ses dossiers/).count()) === 1,
      "le dialogue annonce les dossiers prédéfinis du type",
    )
    await shot(rep, "projet_nouveau")
    await rep.keyboard.press("Escape")
    await rep.waitForTimeout(400)
  }
  const projetOuvert = rep.locator("tbody tr").getByRole("link").first()
  if (await projetOuvert.count()) {
    await projetOuvert.click()
    await rep.waitForURL("**/projets/*", { timeout: 15000 })
    await rep.waitForTimeout(1200)
    expect(
      (await rep.getByRole("button", { name: /Nouveau dossier/ }).count()) === 0,
      "le pays remplit les dossiers du projet, il n'en ouvre pas",
    )
    await shot(rep, "projet_detail_representant")
  }

  await goto(rep, "/dossiers")
  const repDossiers = await rep.locator("tbody tr").count()
  expect(repDossiers <= hqDossiers, `le pays voit au plus autant de dossiers que le siège (${repDossiers})`)
  await shot(rep, "dossiers_representant")

  // Le pays déclare, et importe ses propres classeurs.
  await goto(rep, "/dossiers/import", 1200)
  expect(
    (await rep.textContent("h1"))?.includes("Importer un classeur") ?? false,
    "le pays ouvre l'import de ses dépenses",
  )
  await shot(rep, "import_representant")

  await goto(rep, "/countries")
  expect((await rep.locator("tbody tr").count()) <= 1, "le pays ne voit que son pays")
  expect((await rep.getByRole("button", { name: /Ajouter/ }).count()) === 0, "le pays n'a pas de bouton « Ajouter »")
  await shot(rep, "countries_representant")

  await goto(rep, "/budgets", 1200)
  expect(
    (await rep.getByRole("button", { name: /Attribuer/ }).count()) === 0,
    "le pays n'a pas de bouton « Attribuer une enveloppe »",
  )
  await goto(rep, "/registre", 1200)
  expect(
    (await rep.getByRole("button", { name: "Exporter" }).count()) === 0,
    "le pays n'a pas de menu « Exporter » sur le registre",
  )
  await shot(rep, "budgets_representant")

  // Pages réservées au siège : la garde ramène au tableau de bord.
  for (const chemin of ["/configuration", "/audit", "/corbeille"]) {
    await rep.goto(`${BASE}${chemin}`)
    await rep.waitForURL((url) => url.pathname === "/", { timeout: 10000 }).catch(() => {})
    await rep.waitForTimeout(800)
    expect(new URL(rep.url()).pathname === "/", `${chemin} redirige le pays vers le tableau de bord`)
  }
  expect(
    ((await rep.textContent("main")) ?? "").includes("réservée au siège"),
    "la redirection est expliquée",
  )
  await shot(rep, "garde_siege")

  // --- Mobile : une page interne ne doit pas défiler horizontalement -------
  const mobile = await newPage(browser, { width: 390, height: 844 })
  await login(mobile, "COUNTRY")
  await goto(mobile, "/dossiers")
  const deborde = await mobile.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  )
  expect(!deborde, "la page ne défile pas horizontalement à 390 px")
  await mobile.getByRole("button", { name: "Ouvrir le menu" }).click()
  await mobile.waitForTimeout(500)
  expect((await mobile.getByRole("dialog").count()) > 0, "le menu replié s'ouvre")
  await shot(mobile, "dossiers_mobile")

  console.log("\nErreurs console :", errors.length ? errors : "aucune")
  console.log("Attentes non tenues :", failures.length ? failures : "aucune")
  await browser.close()
  if (errors.length || failures.length) process.exitCode = 1
}

main().catch((e) => {
  console.error(e)
  process.exit(1)
})
