import { ChevronLeft, ChevronRight } from "lucide-react"

import { Button } from "@/components/ui/button"

/** Taille de page par défaut, alignée sur la pagination du serveur. */
export const PAGE_SIZE = 50

interface PaginationProps {
  page: number
  count: number
  pageSize?: number
  onChange: (page: number) => void
  /** Nom de l'objet listé, pour un décompte lisible. */
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
  noun = ["élément", "éléments"],
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(count / pageSize))
  const [singular, plural] = noun

  if (count === 0) return null

  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm">
      <span className="text-muted-foreground">
        {count} {count > 1 ? plural : singular}
        {totalPages > 1 && ` · page ${page} sur ${totalPages}`}
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
            Précédent
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => onChange(page + 1)}
          >
            Suivant
            <ChevronRight className="ml-1 h-4 w-4" />
          </Button>
        </div>
      )}
    </div>
  )
}
