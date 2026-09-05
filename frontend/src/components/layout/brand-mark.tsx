import { BRAND } from "@/lib/brand"
import { cn } from "@/lib/utils"

/**
 * Emblème de l'application.
 *
 * Le logo complet — emblème et signature — reste illisible sous 40 px : seul
 * l'emblème est utilisé aux petites tailles.
 */
export function BrandMark({ className }: { className?: string }) {
  return (
    <img
      src={BRAND.mark}
      alt=""
      aria-hidden
      className={cn("object-contain", className)}
    />
  )
}
