import * as React from "react"

import { cn } from "@/lib/utils"

/**
 * Liste déroulante native, calquée sur le style de `Input`.
 *
 * Les listes de ce module (rôle, pays, année, projet) portent des valeurs
 * simples et bénéficient du comportement natif : navigation clavier, saisie
 * rapide, rendu adapté sur mobile.
 */
function NativeSelect({ className, children, ...props }: React.ComponentProps<"select">) {
  return (
    <select
      data-slot="native-select"
      className={cn(
        "h-8 w-full min-w-0 rounded-lg border border-input bg-transparent px-2.5 py-1 text-base transition-colors outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-input/50 disabled:opacity-50 aria-invalid:border-destructive md:text-sm dark:bg-input/30",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  )
}

export { NativeSelect }
