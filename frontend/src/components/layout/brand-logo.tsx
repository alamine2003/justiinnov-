import { TracesGH } from "@/components/layout/brand-mark"
import { BRAND } from "@/lib/brand"
import { cn } from "@/lib/utils"

/**
 * Logo complet : « JUSTI » suivi du monogramme de Generic Healthcare, qui
 * se lit « JUSTI GH » (`BRAND.name`, décision 92) sans répéter « GH ».
 *
 * Le bleu — le mot et le monogramme — suit la couleur du texte : `text-logo`
 * par défaut (bleu du groupe, clair en thème sombre), et l'écran de
 * connexion le passe en clair sur son panneau marine. Le rouge et l'orange
 * restent les leurs. Le composant redit le nom aux lecteurs d'écran par un
 * texte masqué : le dessin, lui, est ignoré (`aria-hidden`).
 */
export function BrandLogo({ className }: { className?: string }) {
  return (
    <>
      <svg
        viewBox="0 0 3140 831"
        aria-hidden
        focusable="false"
        fill="currentColor"
        className={cn("shrink-0 text-logo", className)}
      >
        {/*
          Le mot est du texte, pas un tracé : il suit la police de
          l'interface. `textLength` fixe sa largeur dans le repère du logo,
          pour que l'ensemble garde ses proportions quelle que soit la
          police chargée ; sa hauteur de capitale rejoint celle du « GH ».
        */}
        <text
          x="0"
          y="830"
          fontSize="750"
          fontWeight="700"
          fontFamily="var(--font-heading)"
          textLength="2080"
          lengthAdjust="spacingAndGlyphs"
        >
          {BRAND.mot}
        </text>
        <g transform="translate(2228 0)">
          <TracesGH />
        </g>
      </svg>
      <span className="sr-only">{BRAND.name}</span>
    </>
  )
}
