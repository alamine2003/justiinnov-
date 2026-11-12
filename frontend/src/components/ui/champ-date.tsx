import { useState } from "react"
import { Popover } from "@base-ui/react/popover"
import { CalendarDays, ChevronDown, ChevronLeft, ChevronRight, ChevronUp } from "lucide-react"
import { useTranslation } from "react-i18next"
import { DayPicker, type ChevronProps } from "react-day-picker"
import { enGB, fr } from "react-day-picker/locale"
import { Button } from "@/components/ui/button"
import { currentLanguage } from "@/i18n"
import { cn, formatDay, parseLocalDate } from "@/lib/utils"

/** « AAAA-MM-JJ » d'une date, en heure locale : la valeur du champ de date natif. */
function versIso(date: Date): string {
  const mois = String(date.getMonth() + 1).padStart(2, "0")
  const jour = String(date.getDate()).padStart(2, "0")
  return `${date.getFullYear()}-${mois}-${jour}`
}

/** Les années que le calendrier propose : des premiers essais à cinq ans devant. */
const PREMIER_MOIS = new Date(2020, 0)
const DERNIER_MOIS = new Date(new Date().getFullYear() + 5, 11)

/** Mois précédent, mois suivant : l'allure d'un bouton `ghost` en icône. */
const BOUTON_DE_MOIS =
  "inline-flex h-8 w-8 items-center justify-center rounded-lg transition-colors outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-40"

function Chevron({ orientation, className }: ChevronProps) {
  const Icone =
    orientation === "left"
      ? ChevronLeft
      : orientation === "up"
        ? ChevronUp
        : orientation === "down"
          ? ChevronDown
          : ChevronRight
  return <Icone aria-hidden className={cn("h-4 w-4", className)} />
}

/**
 * Champ de date de l'application, à la place du champ de date natif (`input` de type `date`).
 *
 * Le sélecteur natif est dessiné par le navigateur : minuscule sous Safari,
 * dans la langue du navigateur et non de l'interface, et impossible à
 * régler en CSS. Celui-ci est un bouton qui a l'allure d'un `<Input>` et
 * ouvre un calendrier (`react-day-picker`) dans un popover base-ui : jours
 * de 40 px, semaine du lundi, mois et année en listes, au clavier (Tab
 * jusqu'à la grille, puis flèches, Page précédente / suivante, Entrée),
 * dans la langue de l'interface.
 *
 * La valeur reste la chaîne « AAAA-MM-JJ » (ou vide) qu'échangeait le champ
 * natif : les écrans et l'API n'en voient pas la différence. `id` va au
 * bouton, que le `<Label htmlFor>` nomme. `effacable` ajoute « Effacer »,
 * pour un filtre qui peut rester sans date.
 */
export function ChampDate({
  id,
  value,
  onChange,
  effacable = false,
  className,
  "aria-invalid": invalide,
}: {
  id: string
  value: string
  onChange: (valeur: string) => void
  effacable?: boolean
  className?: string
  "aria-invalid"?: boolean
}) {
  const { t } = useTranslation()
  const [ouvert, setOuvert] = useState(false)
  const choisie = value ? parseLocalDate(value) ?? undefined : undefined
  const [mois, setMois] = useState<Date>(() => choisie ?? new Date())

  function changerOuverture(suivant: boolean) {
    // Rouvert, le calendrier montre le mois de la date choisie.
    if (suivant) setMois(choisie ?? new Date())
    setOuvert(suivant)
  }

  function choisir(date: Date | undefined) {
    if (!date) return
    onChange(versIso(date))
    setOuvert(false)
  }

  return (
    <Popover.Root open={ouvert} onOpenChange={changerOuverture}>
      <Popover.Trigger
        id={id}
        type="button"
        aria-invalid={invalide || undefined}
        className={cn(
          "flex h-8 w-full min-w-0 items-center justify-between gap-2 rounded-lg border border-input bg-transparent px-2.5 py-1 text-left text-base transition-colors outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 md:text-sm dark:bg-input/30",
          className,
        )}
      >
        <span className={cn("truncate", !choisie && "text-muted-foreground")}>
          {choisie ? formatDay(value) : t("champ_date.choisir")}
        </span>
        <CalendarDays aria-hidden className="h-4 w-4 shrink-0 text-muted-foreground" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner className="isolate z-50 outline-none" side="bottom" align="start" sideOffset={4}>
          <Popover.Popup
            data-slot="champ-date"
            className="z-50 origin-(--transform-origin) rounded-xl bg-popover p-3 text-popover-foreground shadow-md ring-1 ring-foreground/10 outline-none data-open:animate-in data-open:fade-in-0 data-open:zoom-in-95 data-closed:animate-out data-closed:fade-out-0 data-closed:zoom-out-95"
          >
            <DayPicker
              mode="single"
              selected={choisie}
              onSelect={choisir}
              month={mois}
              onMonthChange={setMois}
              locale={currentLanguage() === "en" ? enGB : fr}
              captionLayout="dropdown"
              startMonth={PREMIER_MOIS}
              endMonth={DERNIER_MOIS}
              showOutsideDays
              components={{ Chevron }}
              classNames={{
                root: "relative",
                months: "flex flex-col",
                month: "space-y-3",
                nav: "absolute top-0 right-0 flex items-center gap-1",
                button_previous: BOUTON_DE_MOIS,
                button_next: BOUTON_DE_MOIS,
                month_caption: "flex h-8 items-center pr-20",
                dropdowns: "flex items-center gap-1.5",
                dropdown_root: "relative rounded-lg border border-input focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/50",
                dropdown: "absolute inset-0 cursor-pointer opacity-0",
                caption_label: "flex h-8 items-center gap-1 px-2 text-sm font-medium",
                month_grid: "border-collapse",
                weekdays: "flex",
                weekday: "w-10 text-center text-xs font-medium text-muted-foreground capitalize",
                weeks: "",
                week: "mt-1 flex",
                day: "p-0 text-center",
                day_button:
                  "inline-flex h-10 w-10 items-center justify-center rounded-lg text-sm transition-colors outline-none hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50",
                selected: "[&>button]:bg-primary [&>button]:text-primary-foreground [&>button]:hover:bg-primary",
                today: "[&>button]:font-semibold [&>button]:ring-1 [&>button]:ring-border",
                outside: "text-muted-foreground/60",
                disabled: "opacity-40",
                hidden: "invisible",
              }}
            />
            {effacable && value && (
              <div className="mt-2 flex justify-end border-t border-border/60 pt-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    onChange("")
                    setOuvert(false)
                  }}
                >
                  {t("champ_date.effacer")}
                </Button>
              </div>
            )}
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  )
}
