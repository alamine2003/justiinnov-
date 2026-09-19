import { ChevronLeft, ChevronRight } from "lucide-react"
import { useTranslation } from "react-i18next"

import { Button } from "@/components/ui/button"
import { pluralize } from "@/lib/utils"

/** Taille de page par défaut, alignée sur la pagination du serveur. */
export const PAGE_SIZE = 50

interface PaginationProps {
  page: number
  count: number
  pageSize?: number
  onChange: (page: number) => void
  /** Nom de l'objet listé, déjà traduit, pour un décompte lisible. */
  noun?: [singular: string, plural: string]
}

/**
 * Contrôle de pagination.
 *
 * Indispensable dès qu'une liste peut dépasser une page : sans lui, seules les
 * premières lignes seraient affichées, sans que rien ne signale les autres.
 */
export function Pagination({
  page,
  count,
  pageSize = PAGE_SIZE,
  onChange,
  noun,
}: PaginationProps) {
  const { t } = useTranslation()
  const totalPages = Math.max(1, Math.ceil(count / pageSize))

  if (count === 0) return null

  // « 1234 dossiers » plutôt que « 1 234 dossiers » : un compte est un
  // nombre affiché, il passe par `Intl` comme les autres.
  const label = noun ? pluralize(count, noun[0], noun[1]) : t("commun.elements", { count })

  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm">
      <span className="text-muted-foreground">
        {label}
        {totalPages > 1 && ` · ${t("commun.page_sur", { page, total: totalPages })}`}
      </span>
      {totalPages > 1 && (
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => onChange(page - 1)}
          >
            <ChevronLeft className="mr-1 h-4 w-4" />
            {t("commun.precedent")}
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => onChange(page + 1)}
          >
            {t("commun.suivant")}
            <ChevronRight className="ml-1 h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  )
}
