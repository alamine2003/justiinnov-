/**
 * Échelle commune des barres d'enveloppe.
 *
 * C'est une longueur, pas un chiffre affiché : comme les primitives de
 * `components/ui/charts.tsx`, ce module compose des montants du serveur pour
 * dessiner, jamais pour dire un solde, un écart ni un taux — voir « Rien ne
 * se calcule dans l'interface » dans DESIGN.md. Il vit à part pour que deux
 * pages ne le recopient pas chacune de leur côté.
 */

/** Ce qu'une barre d'enveloppe lit d'une ligne, telle que le serveur l'envoie. */
export interface LigneEnveloppe {
  allocated: string
  consumed: string
  engaged: string
}

/**
 * Échelle commune à une liste de barres : la plus grande enveloppe attribuée,
 * ou la plus grosse dépense lorsqu'elle la dépasse. L'engagé y compte, car la
 * barre le dessine après le consommé et un dépassement mesuré sur les deux
 * sortirait sinon du cadre. Sans ligne, `1`, pour ne pas diviser par zéro.
 *
 * C'est une longueur, pas un chiffre affiché : deux pays ne se comparent qu'à
 * échelle égale, et le calcul appartient donc à ce fichier, pas aux pages.
 */
export function echelleCommune(rows: readonly LigneEnveloppe[]): number {
  return Math.max(
    ...rows.map((row) =>
      Math.max(Number(row.allocated), Number(row.consumed) + Number(row.engaged)),
    ),
    1,
  )
}
