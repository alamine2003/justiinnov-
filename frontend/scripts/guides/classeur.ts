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
