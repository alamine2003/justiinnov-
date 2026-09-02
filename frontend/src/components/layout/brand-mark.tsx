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

/** Emblème, nom et version — l'identité complète, en ligne. */
export function BrandLockup({
  className,
  subtitle,
  showVersion = true,
}: {
  className?: string
  subtitle?: string
  showVersion?: boolean
}) {
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <BrandMark className="h-9 w-9 shrink-0" />
      <div className="leading-tight">
        <p className="flex items-center gap-1.5 font-semibold tracking-tight">
          {BRAND.name}
          {showVersion && (
            <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
              v{BRAND.version}
            </span>
          )}
        </p>
        {subtitle && (
          <p className="text-xs text-muted-foreground">{subtitle}</p>
        )}
      </div>
    </div>
  )
}
