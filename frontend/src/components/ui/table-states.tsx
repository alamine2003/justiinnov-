import type { LucideIcon } from "lucide-react"

import { TableCell, TableRow } from "@/components/ui/table"

/**
 * Ligne vide d'un tableau.
 *
 * Un tableau sans données doit dire *pourquoi* il est vide et, si possible,
 * quoi faire — un simple « Aucune donnée » laisse l'utilisateur sans issue.
 */
export function EmptyRow({
  colSpan,
  icon: Icon,
  title,
  hint,
}: {
  colSpan: number
  icon?: LucideIcon
  title: string
  hint?: string
}) {
  return (
    <TableRow className="hover:bg-transparent">
      <TableCell colSpan={colSpan} className="h-32 text-center">
        {Icon && (
          <Icon className="mx-auto mb-3 h-7 w-7 text-muted-foreground/40" />
        )}
        <p className="text-sm font-medium text-muted-foreground">{title}</p>
        {hint && (
          <p className="mt-1 text-xs text-muted-foreground/70">{hint}</p>
        )}
      </TableCell>
    </TableRow>
  )
}

/**
 * Lignes de chargement.
 *
 * Occupe la place des vraies lignes plutôt qu'une barre unique : la page ne
 * sursaute pas au moment où les données arrivent.
 */
export function SkeletonRows({
  rows = 4,
  columns,
}: {
  rows?: number
  columns: number
}) {
  return (
    <>
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <TableRow key={rowIndex} className="hover:bg-transparent">
          {Array.from({ length: columns }).map((_, cellIndex) => (
            <TableCell key={cellIndex} className="py-4">
              <div
                className="h-3.5 animate-pulse rounded bg-muted"
                // Des largeurs inégales évoquent du texte, là où des barres
                // identiques font penser à un gabarit figé.
                style={{ width: `${[85, 60, 70, 45][cellIndex % 4]}%` }}
              />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  )
}
