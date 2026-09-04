import { AlertTriangle } from "lucide-react"
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
  noun: string
}) {
  if (!isTruncated(page)) return null
  return (
    <Alert>
      <AlertTriangle className="h-4 w-4" />
      <AlertTitle>Liste incomplète</AlertTitle>
      <AlertDescription>
        Seuls {page!.results.length} {noun} sur {page!.count} sont proposés.
        Affinez la recherche ou contactez le siège.
      </AlertDescription>
    </Alert>
  )
}
