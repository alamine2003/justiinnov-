import { formatAmount } from "@/lib/utils"

/**
 * Montant tel qu'il figure sur la pièce, quand la dépense a été décaissée
 * dans une autre devise.
 *
 * Sans lui, le contrôleur ne lirait que la conversion — un chiffre qui
 * n'apparaît sur aucun justificatif, et qu'il ne pourrait donc rapprocher
 * de rien.
 */
export function OriginalAmount({
  currency,
  amount,
}: {
  currency: string
  amount: string | null
}) {
  if (!currency || amount === null) return null
  return (
    <span className="block text-xs font-normal text-muted-foreground">
      soit {formatAmount(amount, currency)} sur la pièce
    </span>
  )
}
