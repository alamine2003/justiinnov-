import * as React from "react"

import { cn } from "@/lib/utils"

/**
 * Zone qui défile dans sa boîte — un tableau, un graphique trop large, une
 * liste à hauteur d'écran : une région nommée, atteignable au clavier. Sans
 * elle, une zone sans lien ni bouton ne défilerait qu'à la souris (WCAG
 * 2.1.1, contrôle d'accessibilité des captures, décision 129).
 */
export function ZoneDefilante({
  label,
  className,
  ...props
}: React.ComponentProps<"section"> & { label: string }) {
  return (
    // Une `section` nommée est une région. Le focus clavier sur une zone qui
    // défile est la technique attendue (axe, scrollable-region-focusable) :
    // la règle générique qui le refuse aux éléments non interactifs se lève
    // ici seulement.
    <section
      aria-label={label}
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
      tabIndex={0}
      className={cn("outline-none focus-visible:ring-3 focus-visible:ring-ring/50", className)}
      {...props}
    />
  )
}
