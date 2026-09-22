import { Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

/**
 * Indicateur d'un rechargement en arrière-plan : la page reste affichée, une
 * petite roue tourne à côté de ce qui va changer.
 *
 * L'icône est masquée aux lecteurs d'écran et le libellé leur est donné en
 * `sr-only` : un `aria-label` posé sur un `<svg>` sans rôle n'est pas lu.
 * Trois pages portaient chacune leur roue avec ce défaut.
 */
export function RefreshIndicator({ label, className }: { label: string; className?: string }) {
  return (
    <output className={cn("inline-flex items-center align-middle", className)}>
      <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-hidden />
      <span className="sr-only">{label}</span>
    </output>
  )
}
