import { useTranslation } from "react-i18next"
import { formatAmount, normalizeDecimal } from "@/lib/utils"

/**
 * Écho d'un montant saisi : ce que le serveur enregistrera.
 *
 * `normalizeDecimal` tranche l'ambiguïté des séparateurs d'après la langue de
 * l'interface — en français, « 150,000 » vaut cent cinquante, pas cent
 * cinquante mille. La règle est délibérée, mais elle s'appliquait en silence :
 * un manager habitué aux montants anglo-saxons enregistrait 150 FCFA au lieu
 * de 150 000, et l'écart ne se voyait qu'au rapprochement de la pièce.
 *
 * L'écho ne s'affiche que là où l'ambiguïté existe — une saisie qui porte un
 * séparateur. « 150000 » ne se lit que d'une façon : le répéter serait du
 * bruit.
 */
export function MontantNormalise({
  value,
  currency,
}: {
  value: string
  /** Devise affichée à côté du montant, quand l'écran la connaît. */
  currency?: string
}) {
  const { t } = useTranslation()
  const normalise = normalizeDecimal(value)
  if (normalise === null || !/[.,]/.test(value)) return null
  return (
    <p className="text-xs text-muted-foreground">
      {t("commun.sera_enregistre", { montant: formatAmount(normalise, currency) })}
    </p>
  )
}
