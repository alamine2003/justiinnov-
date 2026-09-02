import { BRAND, copyright } from "@/lib/brand"

/**
 * Pied de page : identité, version et auteur.
 *
 * Présent sur chaque écran plutôt que sur une page « à propos » : la version
 * qui tourne est la première chose qu'on demande quand un comportement
 * surprend.
 */
export function AppFooter() {
  return (
    <footer className="mt-12 border-t border-border/60 bg-card/40">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-2 px-6 py-6 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <p>
          {copyright()}{" "}
          <span className="text-muted-foreground/70">{BRAND.tagline}.</span>
        </p>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span>
            Version <span className="font-medium text-foreground">{BRAND.version}</span>
          </span>
          <span aria-hidden className="text-border">·</span>
          <span>
            Développé par{" "}
            <span className="font-medium text-foreground">{BRAND.developer}</span>
          </span>
        </p>
      </div>
    </footer>
  )
}
