import { useState } from "react"
import { Download, FileSpreadsheet, FileText, Loader2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { NativeSelect } from "@/components/ui/native-select"
import { MonthSelect, type MonthValue } from "@/components/reporting/month-select"
import { useAuth } from "@/context/use-auth"
import {
  downloadExport,
  TABULAR_FORMATS,
  type ExportKind,
  type TabularFormat,
} from "@/lib/reporting"

const CURRENT_YEAR = new Date().getFullYear()
const YEARS = [CURRENT_YEAR + 1, CURRENT_YEAR, CURRENT_YEAR - 1, CURRENT_YEAR - 2]

interface ExportMenuProps {
  /** Exercice repris des filtres de l'écran ; absent, le menu propose le sien. */
  year?: number
  /** Pays repris des filtres de l'écran ; absent ou vide, tout le périmètre. */
  country?: number | ""
  /** Reçoit l'échec d'un export, pour l'afficher dans l'alerte de la page. */
  onError?: (message: string | null) => void
}

/**
 * Menu « Exporter » : dépenses et rapprochement en Excel, CSV ou Word, et
 * rapport PDF, sur l'exercice ou l'un de ses mois.
 *
 * Réservé aux administrateurs par défaut (`data.export`) : pour les autres rôles, ni
 * bouton ni lien. Le fichier passe par la vue authentifiée, jamais par une
 * URL construite à la main ; chaque export est inscrit au journal d'audit.
 */
export function ExportMenu({ year, country, onError }: ExportMenuProps) {
  const { t } = useTranslation()
  const { can } = useAuth()
  const [ownYear, setOwnYear] = useState(CURRENT_YEAR)
  const [month, setMonth] = useState<MonthValue>("")
  const [exporting, setExporting] = useState<ExportKind | null>(null)

  if (!can("data.export")) return null

  const exercice = year ?? ownYear

  const run = async (kind: ExportKind) => {
    setExporting(kind)
    onError?.(null)
    try {
      await downloadExport(kind, { year: exercice, month: month || null, country })
    } catch (e) {
      onError?.(e instanceof Error ? e.message : t("exports.impossible"))
    } finally {
      setExporting(null)
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {year === undefined && (
        <NativeSelect
          value={ownYear}
          onChange={(e) => setOwnYear(Number(e.target.value))}
          aria-label={t("commun.annee")}
          className="w-28"
        >
          {YEARS.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </NativeSelect>
      )}
      <MonthSelect value={month} onChange={setMonth} className="w-40" />
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button variant="outline" disabled={exporting !== null}>
              {exporting ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Download className="mr-2 h-4 w-4" aria-hidden />
              )}
              {t("exports.exporter")}
            </Button>
          }
        />
        <DropdownMenuContent align="end" className="min-w-56">
          <ExportGroup family="expenses" label={t("exports.depenses")} onSelect={run} />
          <DropdownMenuSeparator />
          <ExportGroup family="reconciliation" label={t("exports.rapprochement")} onSelect={run} />
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => void run("report.pdf")}>
            <FileText aria-hidden />
            {t("exports.rapport_pdf")}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <p className="px-1.5 py-1 text-xs text-muted-foreground">{t("exports.audit_note")}</p>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}

function ExportGroup({
  family,
  label,
  onSelect,
}: {
  family: "expenses" | "reconciliation"
  label: string
  onSelect: (kind: ExportKind) => Promise<void>
}) {
  const { t } = useTranslation()
  return (
    <DropdownMenuGroup>
      <DropdownMenuLabel>{label}</DropdownMenuLabel>
      {TABULAR_FORMATS.map((format: TabularFormat) => (
        <DropdownMenuItem key={format} onClick={() => void onSelect(`${family}.${format}`)}>
          <FileSpreadsheet aria-hidden />
          {t(`exports.formats.${format}`)}
        </DropdownMenuItem>
      ))}
    </DropdownMenuGroup>
  )
}
