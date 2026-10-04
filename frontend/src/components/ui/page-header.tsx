import type { ReactNode } from "react"

/**
 * En-tête de page : titre, phrase d'explication et actions.
 *
 * Chaque écran répétait ce bloc avec des espacements légèrement différents.
 * Le centraliser garantit un rythme identique d'une page à l'autre.
 */
export function PageHeader({
  title,
  description,
  children,
}: {
  title: string
  description?: ReactNode
  /** Actions principales de la page, alignées à droite. */
  children?: ReactNode
}) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-4 court:gap-3">
      <div className="max-w-2xl">
        <h1 className="text-2xl font-semibold tracking-tight court:text-xl">{title}</h1>
        {description && (
          <p className="mt-1.5 text-sm text-muted-foreground court:mt-1">{description}</p>
        )}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </header>
  )
}
