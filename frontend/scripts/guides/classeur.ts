/**
 * Un classeur Excel minimal, écrit à la volée pour le guide d'import.
 *
 * Le guide importe un classeur au format historique (N°ORDRE, DATE, TEAM,
 * OWNER… : `backend/reporting/imports.py`), aux noms de la démonstration
 * et dans la langue filmée. Le fabriquer ici évite un fichier binaire dans
 * le dépôt, qu'on ne saurait ni relire ni régénérer.
 *
 * Un xlsx est une archive ZIP de quelques fichiers XML. Les entrées sont
 * stockées sans compression : il suffit d'en écrire les en-têtes.
 *
 * Le module tient aussi les dates du tournage, calculées à partir du jour
 * où il se joue, et la vérification de ce que l'API répond à l'import. Tout
 * y est pur — l'horloge se passe en argument —, donc testé sans base ni
 * navigateur (`classeur.test.mts`).
 */
import { crc32 } from "node:zlib"

type Cellule = string | number

function echapper(texte: string) {
  return texte.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;")
}

/** `0` → `A`, `25` → `Z` : les guides n'ont pas besoin de plus de colonnes. */
function colonne(i: number) {
  return String.fromCharCode(65 + i)
}

function feuille(lignes: Cellule[][]) {
  const corps = lignes
    .map((cellules, l) => {
      const xml = cellules
        .map((valeur, c) => {
          const ref = `${colonne(c)}${l + 1}`
          return typeof valeur === "number"
            ? `<c r="${ref}"><v>${valeur}</v></c>`
            : `<c r="${ref}" t="inlineStr"><is><t>${echapper(valeur)}</t></is></c>`
        })
        .join("")
      return `<row r="${l + 1}">${xml}</row>`
    })
    .join("")
  return (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' +
    `<sheetData>${corps}</sheetData></worksheet>`
  )
}

const FICHIERS_FIXES: Record<string, string> = {
  "[Content_Types].xml":
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
    '<Default Extension="xml" ContentType="application/xml"/>' +
    '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
    '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' +
    "</Types>",
  "_rels/.rels":
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>' +
    "</Relationships>",
  "xl/workbook.xml":
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" ' +
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">' +
    '<sheets><sheet name="Feuil1" sheetId="1" r:id="rId1"/></sheets></workbook>',
  "xl/_rels/workbook.xml.rels":
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>' +
    "</Relationships>",
}

/** Une archive ZIP aux entrées stockées (méthode 0), sans dossier ni commentaire. */
function archive(fichiers: Record<string, string>) {
  const locaux: Buffer[] = []
  const centraux: Buffer[] = []
  let decalage = 0
  for (const [nom, contenu] of Object.entries(fichiers)) {
    const donnees = Buffer.from(contenu, "utf8")
    const nomOctets = Buffer.from(nom, "utf8")
    const somme = crc32(donnees)
    const local = Buffer.alloc(30)
    local.writeUInt32LE(0x04034b50, 0)
    local.writeUInt16LE(20, 4)
    local.writeUInt16LE(0, 6)
    local.writeUInt16LE(0, 8)
    local.writeUInt32LE(0, 10)
    local.writeUInt32LE(somme, 14)
    local.writeUInt32LE(donnees.length, 18)
    local.writeUInt32LE(donnees.length, 22)
    local.writeUInt16LE(nomOctets.length, 26)
    local.writeUInt16LE(0, 28)
    const central = Buffer.alloc(46)
    central.writeUInt32LE(0x02014b50, 0)
    central.writeUInt16LE(20, 4)
    central.writeUInt16LE(20, 6)
    central.writeUInt16LE(0, 8)
    central.writeUInt16LE(0, 10)
    central.writeUInt32LE(0, 12)
    central.writeUInt32LE(somme, 16)
    central.writeUInt32LE(donnees.length, 20)
    central.writeUInt32LE(donnees.length, 24)
    central.writeUInt16LE(nomOctets.length, 28)
    central.writeUInt32LE(decalage, 42)
    locaux.push(local, nomOctets, donnees)
    centraux.push(central, nomOctets)
    decalage += local.length + nomOctets.length + donnees.length
  }
  const repertoire = Buffer.concat(centraux)
  const fin = Buffer.alloc(22)
  fin.writeUInt32LE(0x06054b50, 0)
  const nombre = Object.keys(fichiers).length
  fin.writeUInt16LE(nombre, 8)
  fin.writeUInt16LE(nombre, 10)
  fin.writeUInt32LE(repertoire.length, 12)
  fin.writeUInt32LE(decalage, 16)
  return Buffer.concat([...locaux, repertoire, fin])
}

/** Le classeur d'une seule feuille, la première ligne servant d'en-tête. */
export function classeur(lignes: Cellule[][]) {
  return archive({ ...FICHIERS_FIXES, "xl/worksheets/sheet1.xml": feuille(lignes) })
}

// ---------------------------------------------------------------------------
// Les dates du tournage
// ---------------------------------------------------------------------------

/**
 * Le jour du tournage moins `jours`, sans quitter son année. Les dates du
 * guide se calculent à partir du jour où il se tourne : la
 * démonstration (`seed_demo`) n'ouvre que les enveloppes de l'année en
 * cours, et une ligne datée d'une autre année n'en trouverait aucune — le
 * tournage échouait dès le 1er janvier qui suivait. Une date passée, parce
 * qu'une dépense se déclare après coup ; jamais avant le 1er janvier, pour
 * qu'un tournage des premiers jours de l'année trouve encore l'enveloppe.
 */
export function jourDuTournage(aujourdhui: Date, jours: number): Date {
  const annee = aujourdhui.getFullYear()
  const jour = new Date(annee, aujourdhui.getMonth(), aujourdhui.getDate() - jours)
  const premierJanvier = new Date(annee, 0, 1)
  return jour < premierJanvier ? premierJanvier : jour
}

function deuxChiffres(nombre: number) {
  return String(nombre).padStart(2, "0")
}

/**
 * `JJ/MM/AAAA`, le format du classeur historique (`FORMATS_DE_DATE` de
 * `backend/reporting/imports.py`) : jour et mois toujours sur deux
 * chiffres — l'ancien `0${i + 1}/10/2026` donnait « 010/10/2026 » à la
 * dixième ligne, refusée.
 */
export function dateDuClasseur(jour: Date): string {
  return `${deuxChiffres(jour.getDate())}/${deuxChiffres(jour.getMonth() + 1)}/${jour.getFullYear()}`
}

/** `AAAA-MM-JJTHH:MM`, la valeur d'un champ `datetime-local`. */
export function dateDeSaisie(jour: Date, heure = "10:30"): string {
  return `${jour.getFullYear()}-${deuxChiffres(jour.getMonth() + 1)}-${deuxChiffres(jour.getDate())}T${heure}`
}

// ---------------------------------------------------------------------------
// Le classeur du guide d'import, et ce que l'API doit en dire
// ---------------------------------------------------------------------------

/** Les colonnes du classeur historique que le guide remplit. */
export const COLONNES_DU_CLASSEUR = ["N°ORDRE", "DATE", "TEAM", "OWNER", "LIBELLE DES TRANSACTIONS", "DEPENSES"] as const

/**
 * Le classeur du guide d'import, au format historique, aux noms de la
 * démonstration. La ligne `i` est datée de `premierEcart + i` jours avant
 * le tournage : des jours qui précèdent la ligne saisie à la main.
 */
export function classeurDuGuide(
  libelles: readonly string[],
  { aujourdhui, equipe, responsable, premierEcart = 4 }: {
    aujourdhui: Date
    equipe: string
    responsable: string
    premierEcart?: number
  },
) {
  return classeur([
    [...COLONNES_DU_CLASSEUR],
    ...libelles.map((libelle, i) => [
      `G-${i + 1}`,
      dateDuClasseur(jourDuTournage(aujourdhui, premierEcart + i)),
      equipe,
      responsable,
      libelle,
      150000 + i * 25000,
    ]),
  ])
}

/** La réponse de `POST /api/imports/expenses.xlsx` (`reporting.imports._resultat`). */
export interface ResultatDImport {
  lignes_creees?: unknown
  erreurs?: unknown
  dry_run?: unknown
}

/**
 * Vérifie qu'un import (ou sa simulation) a fait exactement ce que le guide
 * montre, et lève sinon. L'API répond 200 même quand elle
 * refuse le classeur, avec une liste `erreurs`, et l'écran affiche alors
 * le même titre de résultat : attendre ce titre laissait filmer une carte
 * d'erreurs sous la légende « Tout est correct ».
 */
export function verifierLImport(
  etape: string,
  statut: number,
  resultat: ResultatDImport,
  attendu: { lignes: number; simulation: boolean },
) {
  const motifs: string[] = []
  if (statut < 200 || statut >= 300) motifs.push(`statut HTTP ${statut}`)
  const erreurs = Array.isArray(resultat.erreurs) ? resultat.erreurs : null
  if (erreurs === null) motifs.push("réponse sans liste « erreurs »")
  else if (erreurs.length > 0) motifs.push(`${erreurs.length} erreur(s) : ${JSON.stringify(erreurs)}`)
  if (resultat.lignes_creees !== attendu.lignes) {
    motifs.push(`lignes_creees vaut ${JSON.stringify(resultat.lignes_creees)}, ${attendu.lignes} attendue(s)`)
  }
  if (resultat.dry_run !== attendu.simulation) {
    motifs.push(`dry_run vaut ${JSON.stringify(resultat.dry_run)}, ${attendu.simulation} attendu`)
  }
  if (motifs.length > 0) throw new Error(`${etape} : le serveur n'a pas fait ce que le guide montre — ${motifs.join(" ; ")}.`)
}
