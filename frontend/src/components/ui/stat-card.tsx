import type { ReactNode } from "react"
import type { LucideIcon } from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"

/**
 * Chiffre mis en avant : libellé en étiquette, valeur en `text-2xl`, contexte
 * en légende. Quatre pages avaient chacune leur copie.
 *
 * `children` accueille ce qui complète le chiffre sans le remplacer — une
 * barre de proportion, par exemple. `tone` borde la carte quand le chiffre
 * lui-même est une mauvaise nouvelle.
 */
export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  tone,
  children,
}: {
  label: string
  value: string | number
  hint?: string
  icon?: LucideIcon
  /** Teinte du chiffre et de la bordure : réservée à un écart, un dépassement. */
  tone?: "danger"
  children?: ReactNode
}) {
  return (
    <Card
      className={cn(
        "shadow-sm",
        tone === "danger" ? "border-destructive/30" : "border-border/60",
      )}
    >
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {Icon && <Icon className="h-3.5 w-3.5" aria-hidden />}
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p
          className={cn(
            "text-2xl font-semibold tracking-tight",
            tone === "danger" && "text-destructive",
          )}
        >
          {value}
        </p>
        {children}
        {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  )
}
