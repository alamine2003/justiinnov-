/**
 * Mettre les pays sur une même échelle.
 *
 * Les montants d'une ligne de pays sont dans la devise de ce pays : une
 * enveloppe en GNF et une enveloppe en XOF ne se comparent pas. Le serveur
 * joint donc à chaque ligne ses montants convertis en FCFA (`*_xof`), et
 * c'est avec eux qu'on dessine — les chiffres lus, eux, restent dans la
 * devise du pays.
 *
 * Une devise sans taux connu reçoit `null` : la ligne se replie sur ses
 * propres montants et se dessine contre sa propre enveloppe. La proportion
 * reste vraie ; la comparaison avec les autres pays n'est pas prétendue, et
 * `converti` à faux permet de le dire à l'écran.
 */

/** Ce que la fonction lit d'une ligne, quelle que soit la route. */
export interface LigneConvertible {
  allocated: string
  consumed: string
  engaged: string
  allocated_xof?: string | null
  consumed_xof?: string | null
  engaged_xof?: string | null
}

export interface Mesure<T> {
  row: T
  /** Vrai quand les trois montants sont exploitables en FCFA. */
  converti: boolean
  allocated: number
  consumed: number
  engaged: number
}

/** Un montant du serveur est utilisable s'il est présent et fini. */
function nombre(valeur: string | null | undefined): number | null {
  if (valeur === null || valeur === undefined) return null
  const n = Number(valeur)
  return Number.isFinite(n) ? n : null
}

export function mesuresEnXof<T extends LigneConvertible>(rows: readonly T[]): Mesure<T>[] {
  return rows.map((row) => {
    const xof = [row.allocated_xof, row.consumed_xof, row.engaged_xof].map(nombre)
    const converti = xof.every((v) => v !== null)
    const [allocated, consumed, engaged] = converti
      ? (xof as number[])
      : [Number(row.allocated) || 0, Number(row.consumed) || 0, Number(row.engaged) || 0]
    return { row, converti, allocated, consumed, engaged }
  })
}

/**
 * L'échelle commune : la plus grande grandeur parmi les lignes converties.
 * Les autres ne pèsent pas dessus — elles n'y sont pas comparables.
 */
export function echelleCommune<T>(mesures: readonly Mesure<T>[]): number {
  return Math.max(
    ...mesures.filter((m) => m.converti).map((m) => Math.max(m.allocated, m.consumed)),
    1,
  )
}

/** L'échelle d'une ligne : la commune si elle y a sa place, la sienne sinon. */
export function echelleDe(
  mesure: Pick<Mesure<unknown>, "converti" | "allocated" | "consumed">,
  commune: number,
): number {
  return mesure.converti ? commune : Math.max(mesure.allocated, mesure.consumed, 1)
}
