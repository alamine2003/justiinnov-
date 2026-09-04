import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

/**
 * Erreur de formulaire : encadré `bg-destructive/10` avec `role="alert"`.
 *
 * Chaque formulaire réécrivait ce paragraphe, et la moitié oubliaient le
 * rôle : l'échec apparaissait à l'écran sans être annoncé aux lecteurs
 * d'écran. Ne rend rien sans message.
 */
export function FormError({
  children,
  className,
}: {
  children?: ReactNode
  className?: string
}) {
  if (!children) return null
  return (
    <p
      role="alert"
      className={cn(
        "rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive",
        className,
      )}
    >
      {children}
    </p>
  )
}
