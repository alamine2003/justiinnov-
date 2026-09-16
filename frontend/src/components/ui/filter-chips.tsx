import { cn } from "@/lib/utils"

export interface FilterChip {
  /** Valeur transmise au serveur ; la chaîne vide vaut « tous ». */
  value: string
  label: string
  /** Compte affiché à côté du libellé, quand le serveur le donne. */
  count?: number
}

/**
 * Un groupe de filtres à bascule, en pastilles. Il remplace une liste
 * déroulante quand les valeurs sont peu nombreuses et qu'on veut les voir
 * toutes : le statut d'un dossier se choisit plus vite qu'il ne se déroule.
 *
 * Chaque pastille est un vrai bouton et expose `aria-pressed` : un lecteur
 * d'écran annonce lequel est actif, comme le veut DESIGN.md.
 */
export function FilterChips({
  chips,
  value,
  onChange,
  label,
  className,
}: {
  chips: FilterChip[]
  value: string
  onChange: (value: string) => void
  /** Ce que le groupe filtre, pour les lecteurs d'écran. */
  label: string
  className?: string
}) {
  return (
    <fieldset className={cn("flex flex-wrap items-center gap-1.5", className)}>
      <legend className="sr-only">{label}</legend>
      {chips.map((chip) => {
        const actif = chip.value === value
        return (
          <button
            key={chip.value || "tous"}
            type="button"
            aria-pressed={actif}
            // Le compte est collé au libellé dans le flux du texte : sans
            // nom explicite, un lecteur d'écran annonce « Tous42 ».
            aria-label={
              chip.count === undefined ? undefined : `${chip.label} · ${chip.count}`
            }
            onClick={() => onChange(chip.value)}
            className={cn(
              "rounded-full border px-3 py-1.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              actif
                ? "border-primary bg-primary font-medium text-primary-foreground"
                : "border-border text-muted-foreground hover:bg-accent/40",
            )}
          >
            {chip.label}
            {chip.count !== undefined && (
              <span className={cn("ml-1.5", !actif && "text-muted-foreground/70")}>
                {chip.count}
              </span>
            )}
          </button>
        )
      })}
    </fieldset>
  )
}
