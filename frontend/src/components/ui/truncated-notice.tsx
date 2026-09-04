import { AlertTriangle } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { isTruncated } from "@/lib/referentiel"
import type { Paginated } from "@/lib/types"

/**
 * Signale qu'une liste chargée d'un bloc (`page_size: 200`) ne contient pas
 * tout : sans cela, un pays absent d'une liste déroulante passerait pour
 * inexistant.
 */
export function TruncatedNotice({
  page,
  noun,
}: {
  page: Paginated<unknown> | null | undefined
  /** Nom des objets listés, déjà traduit, au pluriel. */
  noun: string
}) {
  const { t } = useTranslation()
  if (!isTruncated(page)) return null
  return (
    <Alert>
      <AlertTriangle className="h-4 w-4" />
      <AlertTitle>{t("ui.tronque_titre")}</AlertTitle>
      <AlertDescription>
        {t("ui.tronque_texte", { affiches: page!.results.length, nom: noun, total: page!.count })}
      </AlertDescription>
    </Alert>
  )
}
