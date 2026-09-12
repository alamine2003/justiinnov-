/**
 * Génère l'icône d'onglet et les icônes de l'application installable à
 * partir de `public/favicon.svg` — la tuile : l'emblème blanc sur un carré
 * sombre à coins arrondis (DESIGN.md, « Identité »).
 *
 *   npx tsx scripts/generate-icons.mts
 *
 * Les PNG produits sont versionnés dans `public/` et `public/icons/` : le
 * build n'a pas à dépendre de `sharp`, et l'image Docker n'a pas besoin de
 * ses binaires. L'emblème lui-même vit dans `components/layout/brand-mark.tsx`,
 * tracé depuis `docs/identite/logo-justi-innov.png`.
 */
import { readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import sharp from "sharp"

const racine = join(import.meta.dirname, "../public")
const source = readFileSync(join(racine, "favicon.svg"))

/** Fond de la tuile (`<rect fill>` de `favicon.svg`, #141418), en sRGB. */
const FOND = { r: 20, g: 20, b: 24, alpha: 1 }
const TRANSPARENT = { r: 0, g: 0, b: 0, alpha: 0 }

/**
 * @param chemin fichier produit, relatif à `public/`
 * @param taille côté du carré, en pixels
 * @param opaque vrai pour remplir les coins arrondis avec le fond de la
 *   tuile : iOS et les lanceurs « maskable » rognent eux-mêmes
 * @param echelle part du côté que la tuile occupe. Une icône « maskable »
 *   est rognée en cercle par certains lanceurs : réduite à 74 %, l'emblème
 *   (68 % de la tuile) tient dans la zone sûre — le cercle central de 80 % —
 *   et les bords de la tuile se fondent dans le fond, de même couleur.
 */
async function icone(chemin: string, taille: number, opaque: boolean, echelle = 1) {
  const cote = Math.round(taille * echelle)
  const tuile = await sharp(source, { density: 384 })
    .resize(cote, cote, { fit: "contain", background: TRANSPARENT })
    .png()
    .toBuffer()
  const png = await sharp({
    create: { width: taille, height: taille, channels: 4, background: opaque ? FOND : TRANSPARENT },
  })
    .composite([{ input: tuile, gravity: "centre" }])
    .png()
    .toBuffer()
  writeFileSync(join(racine, chemin), png)
  console.log(`${chemin} (${taille}×${taille})`)
}

await icone("favicon.png", 64, false)
await icone("icons/icon-192.png", 192, false)
await icone("icons/icon-512.png", 512, false)
await icone("icons/icon-maskable-512.png", 512, true, 0.74)
await icone("icons/apple-touch-icon.png", 180, true)
