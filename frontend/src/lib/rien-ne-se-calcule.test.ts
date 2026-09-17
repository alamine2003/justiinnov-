/**
 * Garde-fou de la règle « Rien ne se calcule dans l'interface » (DESIGN.md,
 * CLAUDE.md « Les chiffres se calculent côté serveur »).
 *
 * Les montants arrivent en chaînes décimales et ne se convertissent en nombre
 * qu'au moment de les mettre en forme. Dès qu'une page en compose deux, elle
 * réinvente une formule du serveur — et deux bugs l'ont montré : un
 * dépassement mesuré sur le seul consommé, qui démentait le taux affiché à
 * côté, et une échelle de barres qui laissait le segment de dépassement
 * sortir du cadre.
 *
 * Ce que ce test attrape : une opération arithmétique collée à un
 * `Number(<quelque chose>.<champ monétaire>)`. Ce qu'il n'attrape pas, et il
 * faut le savoir : un montant rangé dans une variable intermédiaire puis
 * composé plus loin — aucune expression régulière ne suit une valeur. Le
 * garde-fou lève les récidives de la forme connue, il ne remplace pas la
 * relecture.
 */
import { readFileSync, readdirSync, statSync } from "node:fs"
import { join, relative } from "node:path"
import { describe, expect, it } from "vitest"

const RACINE = process.cwd()

/**
 * Champs monétaires du serveur, tels que les nomme l'API. `total` et
 * `montant` couvrent les agrégats et les champs de formulaire.
 */
const CHAMPS = [
  "allocated",
  "amount",
  "consumed",
  "engaged",
  "gap",
  "justified",
  "justified_amount",
  "montant",
  "original_amount",
  "remaining",
  "sub_allocated",
  "total",
  "unallocated",
]

const APPEL = new RegExp(`Number\\(\\s*[^()]*\\.(?:${CHAMPS.join("|")})\\b[^()]*\\)`, "g")

/**
 * Seuls fichiers autorisés à composer ces montants : ceux qui dessinent. Ils
 * n'en tirent que des longueurs — largeur de barre, longueur d'arc,
 * coordonnée d'un point, échelle commune —, jamais un chiffre lu par
 * quelqu'un, et leur traduction est vérifiée segment par segment dans
 * `charts.test.tsx` et `echelle.test.ts`. Toute autre adresse est un défaut :
 * cette liste ne s'allonge pas pour faire taire le garde-fou.
 */
const GEOMETRIE = ["src/components/ui/charts.tsx", "src/lib/echelle.ts"]

/** Dossiers d'interface parcourus : tout ce qui affiche des montants. */
const DOSSIERS = ["src/components", "src/pages", "src/lib"]

/**
 * Neutralise les commentaires sans déplacer une ligne : chaque caractère
 * masqué devient une espace. Le `//` précédé de deux-points ou d'un
 * échappement est laissé tel quel, pour ne pas couper une URL en deux.
 */
function sansCommentaires(source: string): string {
  return source
    .replace(/\/\*[\s\S]*?\*\//g, (bloc) => bloc.replace(/[^\n]/g, " "))
    .replace(/(^|[^:"'`\\])\/\/[^\n]*/gm, (trouve, avant: string) =>
      avant + " ".repeat(trouve.length - avant.length),
    )
}

function fichiersSource(dossier: string): string[] {
  return readdirSync(dossier).flatMap((nom) => {
    const chemin = join(dossier, nom)
    if (statSync(chemin).isDirectory()) return fichiersSource(chemin)
    return /\.tsx?$/.test(nom) && !/\.test\.tsx?$/.test(nom) ? [chemin] : []
  })
}

/**
 * Un `-` isolé n'est pas un calcul : il lit un chiffre du serveur dans
 * l'autre sens (`-Number(row.remaining)`, le solde négatif lu en
 * dépassement). On le reconnaît à ce qui le précède : un opérateur, une
 * ouverture, un `return`.
 */
function estSigneUnaire(avant: string): boolean {
  return avant.endsWith("-") && /(?:[=(,:?[{&|;]|\breturn)\s*$/.test(avant.slice(0, -1))
}

interface Infraction {
  ou: string
  extrait: string
}

function infractionsDans(source: string, ou: string): Infraction[] {
  const contenu = sansCommentaires(source)
  const trouvees: Infraction[] = []
  for (const trouve of contenu.matchAll(APPEL)) {
    const debut = trouve.index ?? 0
    const avant = contenu.slice(0, debut).replace(/\s+$/, "")
    const apres = contenu.slice(debut + trouve[0].length).replace(/^\s+/, "")
    const compose =
      (/[-+*/%]$/.test(avant) && !estSigneUnaire(avant)) || /^[-+*/%]/.test(apres)
    if (!compose) continue
    const ligne = contenu.slice(0, debut).split("\n").length
    trouvees.push({ ou: `${ou}:${ligne}`, extrait: trouve[0] })
  }
  return trouvees
}

function infractions(chemin: string): Infraction[] {
  return infractionsDans(readFileSync(chemin, "utf8"), relative(RACINE, chemin))
}

describe("Rien ne se calcule dans l'interface", () => {
  it("aucune page ne compose deux montants du serveur", () => {
    const fichiers = DOSSIERS.flatMap((dossier) => fichiersSource(join(RACINE, dossier))).filter(
      (chemin) => !GEOMETRIE.includes(relative(RACINE, chemin)),
    )

    // Le garde-fou ne vaut que s'il a bien parcouru l'interface : un
    // `fichiersSource` qui ne rendrait rien ne signalerait rien non plus.
    expect(fichiers.length).toBeGreaterThan(50)
    expect(fichiers.flatMap(infractions)).toEqual([])
  })

  it("attrape une composition et laisse passer une lecture", () => {
    expect(
      infractionsDans("const d = Number(row.consumed) + Number(row.engaged)", "temoin"),
    ).toHaveLength(2)
    expect(infractionsDans("const e = Number(a.allocated) - Number(a.total)", "temoin")).toHaveLength(2)

    // Le signe d'un chiffre du serveur reste une lecture, pas un calcul.
    expect(infractionsDans("const d = -Number(row.remaining)", "temoin")).toEqual([])
    expect(infractionsDans("<td>{formatAmount(Number(row.amount))}</td>", "temoin")).toEqual([])
    expect(infractionsDans("if (Number(row.gap) > 0) alerter()", "temoin")).toEqual([])
  })

  it("dit sa limite : un montant rangé dans une variable lui échappe", () => {
    // Le bug d'origine s'écrivait ainsi. Ce test n'est pas un aveu d'échec :
    // il fige ce que le garde-fou ne couvre pas, pour qu'on ne le croie pas
    // plus fort qu'il n'est.
    const source = "const consomme = Number(row.consumed)\nconst depassement = consomme - attribue"

    expect(infractionsDans(source, "temoin")).toEqual([])
  })
})
