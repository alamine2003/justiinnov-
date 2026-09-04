/**
 * Génère les icônes de l'application installable à partir de
 * `public/favicon.svg`, la seule source d'identité vectorielle.
 *
 *   npx tsx scripts/generate-icons.mts
 *
 * Les PNG produits sont versionnés dans `public/icons/` : le build n'a pas à
 * dépendre de `sharp`, et l'image Docker n'a pas besoin de ses binaires.
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import sharp from "sharp"

const racine = join(import.meta.dirname, "../public")
const source = readFileSync(join(racine, "favicon.svg"))
const sortie = join(racine, "icons")
mkdirSync(sortie, { recursive: true })

/** Fond de page du thème clair (`--background`), en sRGB. */
const FOND = { r: 250, g: 250, b: 251, alpha: 1 }

/**
 * @param taille côté du carré, en pixels
 * @param marge part du côté laissée vide autour de l'emblème — une icône
 *   « maskable » est rognée en cercle par certains lanceurs, l'emblème doit
 *   tenir dans la zone sûre (80 % du centre)
 */
async function icone(nom: string, taille: number, marge: number) {
  const interieur = Math.round(taille * (1 - 2 * marge))
  const embleme = await sharp(source, { density: 384 })
    .resize(interieur, interieur, { fit: "contain", background: { ...FOND, alpha: 0 } })
    .png()
    .toBuffer()
  const png = await sharp({
    create: { width: taille, height: taille, channels: 4, background: FOND },
  })
    .composite([{ input: embleme, gravity: "centre" }])
    .png()
    .toBuffer()
  writeFileSync(join(sortie, nom), png)
  console.log(`${nom} (${taille}×${taille})`)
}

await icone("icon-192.png", 192, 0.12)
await icone("icon-512.png", 512, 0.12)
await icone("icon-maskable-512.png", 512, 0.2)
await icone("apple-touch-icon.png", 180, 0.12)
