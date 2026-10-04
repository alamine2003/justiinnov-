import { useTranslation } from "react-i18next"
import { BRAND, copyright } from "@/lib/brand"
import { cn } from "@/lib/utils"

/**
 * Pied de page : identité, version et auteur.
 *
 * Présent sur chaque écran plutôt que sur une page « à propos » : la version
 * qui tourne est la première chose qu'on demande quand un comportement
 * surprend. Dès `lg`, il passe au pied de la barre latérale
 * (`PiedDuMenu`) : la page garde sa hauteur pour son contenu.
 */
export function AppFooter({ className }: { className?: string }) {
  const { t } = useTranslation()
  return (
    <footer className={cn("mt-12 border-t border-border/60 bg-card/40", className)}>
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-2 px-6 py-6 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
        <p>
          {copyright()}{" "}
          <span className="text-muted-foreground/70">{t("app.tagline")}.</span>
        </p>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span>
            {t("layout.version")}{" "}
            <span className="font-medium text-foreground">{BRAND.version}</span>
          </span>
          <span aria-hidden className="text-border">·</span>
          <span>
            {t("layout.developpe_par")}{" "}
            <span className="font-medium text-foreground">{BRAND.developer}</span>
          </span>
        </p>
      </div>
    </footer>
  )
}
