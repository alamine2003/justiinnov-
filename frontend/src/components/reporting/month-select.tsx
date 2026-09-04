import { useTranslation } from "react-i18next"
import { NativeSelect } from "@/components/ui/native-select"
import { MONTHS, monthName } from "@/lib/months"

/** Mois 1 à 12, ou `""` pour l'exercice entier. */
export type MonthValue = number | ""

/**
 * Période d'un export : l'exercice entier ou l'un de ses mois. Le mois ne
 * borne que les exports ; les écrans, eux, restent à l'exercice.
 */
export function MonthSelect({
  value,
  onChange,
  className,
}: {
  value: MonthValue
  onChange: (value: MonthValue) => void
  className?: string
}) {
  const { t } = useTranslation()
  return (
    <NativeSelect
      value={value}
      onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
      aria-label={t("exports.periode_aria")}
      className={className}
    >
      <option value="">{t("exports.exercice_entier")}</option>
      {MONTHS.map((month) => (
        <option key={month} value={month}>
          {monthName(month)}
        </option>
      ))}
    </NativeSelect>
  )
}
