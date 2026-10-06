/**
 * Le contrôle des images d'un guide (décision 118) : la
 * vidéo montre-t-elle, sous chaque sous-titre, ce que la page affichait ?
 *
 * L'enregistrement de Playwright peut perdre des images sans rien dire : la
 * prise française « Ouvrir un projet » de la 2.1.0 est restée figée cinq
 * secondes sur la liste d'avant la création, sous le sous-titre « Le projet
 * est ouvert », alors que le script avait bien attendu la fiche. La
 * relecture à l'œil ne l'avait pas vu. Le tournage compare donc, pour
 * chaque légende, deux images :
 *
 * - la capture de la page que `Scene.dire()` prend `DELAI_DE_LA_CAPTURE`
 *   après le début de la légende : ce que la page montrait ;
 * - l'image de la vidéo réencodée 0,4 s après ce même début : ce que verra
 *   la personne qui lit le sous-titre.
 *
 * Les deux sont réduites à la même petite taille dans le navigateur du
 * tournage, qui décode le PNG (le ffmpeg de Playwright n'a ni décodeur PNG
 * ni sortie brute, et le dépôt ne prend pas de dépendance pour cela), puis
 * comparées pixel à pixel. Au-delà de `SEUIL_D_ECART`, le tournage échoue
 * et rien n'arrive dans `public/guides/`.
 *
 * Seuls `imageDeLaVideo` (ffmpeg) et `pixelsReduits` (le navigateur)
 * touchent au monde ; le reste se teste seul (`controle-images.test.mts`).
 * Le contrôle ne tourne qu'au tournage, sur le poste de qui tourne : la CI
 * ne tourne pas les guides (décision 118).
 */
import { execFile } from "node:child_process"
import { mkdtemp, readFile, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import { promisify } from "node:util"
import type { Browser, Page } from "playwright"
import { horodatage, type Repere } from "./scene.ts"

/**
 * Les instants de la vidéo comparés à la capture, après le début de la
 * légende. 0,4 s d'abord ; si l'image s'en écarte, les suivantes jusqu'à
 * une seconde, et l'on retient la plus proche : l'enregistrement suit la
 * page avec quelques dixièmes de retard au début d'une prise (au premier
 * sous-titre de « Joindre une pièce », la vidéo montre encore le
 * chargement à 0,3 s quand la page est déjà dessinée). Une prise figée,
 * elle, s'écarte sur toute la fenêtre : celle de la 2.1.0 l'était cinq
 * secondes.
 */
export const DECALAGES_DU_CONTROLE = [400, 550, 700, 850, 1000] as const

/**
 * La taille de comparaison, au quart de la prise (1280 × 800) : la
 * réduction moyenne le bruit de compression (VP8 à 300 kb/s). Une taille
 * double ne distingue pas mieux une page d'une autre (voir `SEUIL_D_ECART`).
 */
export const LARGEUR_DE_COMPARAISON = 320
export const HAUTEUR_DE_COMPARAISON = 200

/** Un pixel diffère quand l'une de ses composantes s'écarte de plus de ce nombre de niveaux (sur 255). */
export const SEUIL_DE_NIVEAU = 32

/**
 * La part de pixels différents au-delà de laquelle le tournage échoue.
 * Calibrée sur les prises de la 2.1.0 (commit 9fde848, décision 118), à
 * 320 × 200 et 32 niveaux :
 * - même écran, capture contre vidéo (les dix affiches contre l'image de
 *   la vidéo une seconde avant la fin) : 0,00 % à 0,15 % ;
 * - la prise fautive, fr/ouvrir-un-projet, sous-titre 7 (l'affiche, qui
 *   montre la fiche, contre l'image à 35,98 s, figée sur la liste) : 6,2 % ;
 * - un dialogue ouvert contre la liste sans lui : 8,4 %.
 * Deux pages de même gabarit ne diffèrent que de quelques pour cent : la
 * barre latérale, l'en-tête et le fond blanc ne changent pas. Le seuil se
 * tient donc bas, mais loin au-dessus du bruit. À 640 × 400, la prise
 * fautive ne s'écartait pas davantage (5,2 %) et le bruit montait ; à 24
 * niveaux, le voile d'un dialogue comptait pour 73 % mais le bruit aussi.
 */
export const SEUIL_D_ECART = 0.02

/** L'écart mesuré sous une légende. */
export interface Ecart {
  /** Le numéro du sous-titre, à partir de 1, comme dans le `.vtt`. */
  numero: number
  texte: string
  /** Le premier instant contrôlé (début de la légende + 0,4 s), en millisecondes. */
  instant: number
  /** La plus petite part de pixels différents sur la fenêtre de contrôle, entre 0 et 1. */
  ecart: number
}

/** Les instants de la vidéo où l'on contrôle une légende, en millisecondes. */
export function instantsDuControle(repere: Repere) {
  return DECALAGES_DU_CONTROLE.map((decalage) => repere.debut + decalage)
}

/**
 * La part des pixels qui diffèrent entre deux images de même taille, en
 * RGBA (`ImageData.data`) : un pixel compte quand l'écart de l'une de ses
 * composantes rouge, verte ou bleue dépasse `seuilDeNiveau`. L'opacité ne
 * compte pas : une capture et une image de vidéo sont toutes deux opaques.
 */
export function proportionDifferente(a: ArrayLike<number>, b: ArrayLike<number>, seuilDeNiveau = SEUIL_DE_NIVEAU) {
  if (a.length !== b.length) throw new Error(`Images de tailles différentes (${a.length} et ${b.length} octets).`)
  if (a.length === 0 || a.length % 4 !== 0) throw new Error(`Image RGBA invalide (${a.length} octets).`)
  let differents = 0
  for (let i = 0; i < a.length; i += 4) {
    const ecart = Math.max(Math.abs(a[i] - b[i]), Math.abs(a[i + 1] - b[i + 1]), Math.abs(a[i + 2] - b[i + 2]))
    if (ecart > seuilDeNiveau) differents++
  }
  return differents / (a.length / 4)
}

/** Les légendes dont l'image s'écarte trop de la capture. */
export function ecartsExcessifs(ecarts: readonly Ecart[], seuil = SEUIL_D_ECART) {
  return ecarts.filter((ecart) => ecart.ecart > seuil)
}

/** Un pourcentage lisible, à une décimale : « 6,2 % ». */
export function pourcentage(part: number) {
  return `${(part * 100).toFixed(1).replace(".", ",")} %`
}

/**
 * L'erreur qui arrête le tournage : elle nomme le guide, chaque sous-titre
 * en cause, l'instant contrôlé et l'écart, pour qu'on aille regarder la
 * vidéo au bon endroit.
 */
export function echecDuControle(guide: string, excessifs: readonly Ecart[], seuil = SEUIL_D_ECART) {
  const lignes = excessifs.map(
    (e) =>
      `  sous-titre ${e.numero} (${horodatage(e.instant)}) « ${e.texte} » : ${pourcentage(e.ecart)} des pixels diffèrent`,
  )
  return new Error(
    `Images de ${guide} : la vidéo ne montre pas ce que la page affichait (seuil ${pourcentage(seuil)}).\n` +
      `${lignes.join("\n")}\n` +
      "L'enregistrement a perdu des images : rien n'est copié dans public/guides. Tournez de nouveau, sur une base neuve.",
  )
}

/** Le type d'une image d'après ses premiers octets : le navigateur la décode d'une adresse `data:`. */
export function typeDImage(image: Uint8Array) {
  if (image[0] === 0x89 && image[1] === 0x50 && image[2] === 0x4e && image[3] === 0x47) return "image/png"
  if (image[0] === 0xff && image[1] === 0xd8) return "image/jpeg"
  throw new Error("Image ni PNG ni JPEG.")
}

/**
 * L'image de la vidéo à `instant` (millisecondes), en PNG, extraite par
 * ffmpeg. `-ss` avant `-i` : quand ffmpeg décode, la recherche à l'entrée
 * est exacte (mêmes images, vérifiées octet pour octet, qu'avec `-ss` après
 * `-i`) et ne décode pas toute la vidéo depuis le début.
 */
export async function imageDeLaVideo(ffmpeg: string, video: string, instant: number) {
  const dossier = await mkdtemp(path.join(tmpdir(), "guides-controle-"))
  const sortie = path.join(dossier, "image.png")
  try {
    await promisify(execFile)(ffmpeg, [
      "-hide_banner", "-loglevel", "error", "-y", "-ss", (instant / 1000).toFixed(3), "-i", video,
      "-frames:v", "1", "-c:v", "png", "-f", "image2", "-update", "1", sortie,
    ])
    const image = await readFile(sortie).catch(() => Buffer.alloc(0))
    if (!image.length) throw new Error(`Aucune image à ${horodatage(instant)} dans ${video}.`)
    return image
  } finally {
    await rm(dossier, { recursive: true, force: true })
  }
}

/**
 * Décode des images (PNG ou JPEG) dans une page vierge du navigateur et
 * les rend réduites à la taille de comparaison, en RGBA. Les deux images
 * d'une comparaison suivent exactement le même chemin. Les pixels
 * reviennent en base64 : un tableau de nombres de 256 000 cases coûtait
 * plusieurs secondes de sérialisation par comparaison.
 *
 * La fonction passée à la page ne déclare aucune fonction nommée : `tsx`
 * leur ajoute des appels (`__name`) qui n'existent pas dans la page (voir
 * `POINTEUR`, `scene.ts`).
 */
export async function pixelsReduits(page: Page, images: readonly Uint8Array[]) {
  const encodes = await page.evaluate(
    async ({ adresses, largeur, hauteur }) => {
      const resultats: string[] = []
      for (const adresse of adresses) {
        const image = new Image()
        image.src = adresse
        await image.decode()
        const toile = document.createElement("canvas")
        toile.width = largeur
        toile.height = hauteur
        const contexte = toile.getContext("2d")
        if (!contexte) throw new Error("Contexte 2D indisponible.")
        contexte.imageSmoothingEnabled = true
        contexte.imageSmoothingQuality = "high"
        contexte.drawImage(image, 0, 0, largeur, hauteur)
        const donnees = contexte.getImageData(0, 0, largeur, hauteur).data
        let binaire = ""
        for (let i = 0; i < donnees.length; i += 0x8000) {
          binaire += String.fromCharCode(...donnees.subarray(i, i + 0x8000))
        }
        resultats.push(btoa(binaire))
      }
      return resultats
    },
    {
      adresses: images.map((image) => `data:${typeDImage(image)};base64,${Buffer.from(image).toString("base64")}`),
      largeur: LARGEUR_DE_COMPARAISON,
      hauteur: HAUTEUR_DE_COMPARAISON,
    },
  )
  return encodes.map((encode) => new Uint8Array(Buffer.from(encode, "base64")))
}

/** L'écart entre deux images, mesuré à la taille de comparaison. */
export async function ecartEntre(page: Page, a: Uint8Array, b: Uint8Array) {
  const [pixelsA, pixelsB] = await pixelsReduits(page, [a, b])
  return proportionDifferente(pixelsA, pixelsB)
}

/**
 * L'écart retenu pour une légende : le plus petit sur la fenêtre de
 * contrôle. `mesurer` rend l'écart à un instant ; on s'arrête dès qu'un
 * instant passe sous le seuil, la plupart des légendes ne coûtent donc
 * qu'une image.
 */
export async function ecartSurLaFenetre(
  instants: readonly number[],
  mesurer: (instant: number) => Promise<number>,
  seuil = SEUIL_D_ECART,
) {
  let plusPetit = Number.POSITIVE_INFINITY
  for (const instant of instants) {
    plusPetit = Math.min(plusPetit, await mesurer(instant))
    if (plusPetit <= seuil) break
  }
  return plusPetit
}

/**
 * Compare, légende par légende, la capture de la page à la vidéo
 * réencodée. Lève `echecDuControle` si l'une s'écarte au-delà du seuil ;
 * rend sinon les écarts mesurés, que le tournage affiche : ils servent à
 * recalibrer le seuil.
 */
export async function controlerLesImages(options: {
  navigateur: Browser
  ffmpeg: string
  video: string
  reperes: readonly Repere[]
  captures: readonly Uint8Array[]
  guide: string
}) {
  const { navigateur, ffmpeg, video, reperes, captures, guide } = options
  if (captures.length !== reperes.length) {
    throw new Error(`${guide} : ${captures.length} captures pour ${reperes.length} légendes.`)
  }
  const page = await navigateur.newPage()
  try {
    const ecarts: Ecart[] = []
    for (const [i, repere] of reperes.entries()) {
      const instants = instantsDuControle(repere)
      const ecart = await ecartSurLaFenetre(instants, async (instant) =>
        ecartEntre(page, captures[i], await imageDeLaVideo(ffmpeg, video, instant)),
      )
      ecarts.push({ numero: i + 1, texte: repere.texte, instant: instants[0], ecart })
    }
    const excessifs = ecartsExcessifs(ecarts)
    if (excessifs.length) throw echecDuControle(guide, excessifs)
    return ecarts
  } finally {
    await page.close()
  }
}
