import { EMBLEME } from "@/components/layout/brand-mark"
import { BRAND } from "@/lib/brand"
import { cn } from "@/lib/utils"

/**
 * Logo complet : l'emblème suivi du nom de l'application (`BRAND.name`,
 * « JUSTI GH », décision 92). En attendant le logo de Generic Healthcare,
 * l'emblème reste le « J » de l'application ; le logo du groupe prendra sa
 * place ici même.
 *
 * En `currentColor`, comme l'emblème (`BrandMark`) : il prend la couleur du
 * texte qui l'entoure, dans les deux thèmes et sur le panneau sombre de la
 * connexion. Le composant redit le nom aux lecteurs d'écran par un texte
 * masqué : le dessin, lui, est ignoré (`aria-hidden`).
 */
export function BrandLogo({ className }: { className?: string }) {
  return (
    <>
      <svg
        viewBox="0 0 1240 297"
        aria-hidden
        focusable="false"
        fill="currentColor"
        className={cn("shrink-0", className)}
      >
        <path d={EMBLEME} />
        {/*
          Le nom est du texte, pas un tracé : il suit la police de
          l'interface. `textLength` fixe sa largeur dans le repère du logo,
          pour que l'ensemble garde ses proportions quelle que soit la
          police chargée.
        */}
        <text
          x="330"
          y="232"
          fontSize="200"
          fontWeight="700"
          fontFamily="var(--font-heading)"
          textLength="900"
          lengthAdjust="spacingAndGlyphs"
        >
          {BRAND.name}
        </text>
      </svg>
      <span className="sr-only">{BRAND.name}</span>
    </>
  )
}
