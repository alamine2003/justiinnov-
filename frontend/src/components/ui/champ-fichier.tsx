import * as React from "react"
import { Upload } from "lucide-react"
import { useTranslation } from "react-i18next"

import { cn } from "@/lib/utils"

/**
 * Un champ fichier dans la langue de l'interface.
 *
 * Le `<input type="file">` natif écrit « Choisir un fichier » ou « Choose
 * File » dans la langue du navigateur, pas dans celle de l'interface : une
 * interface en anglais sur un navigateur français mélangeait les deux. Le
 * champ natif reste le vrai contrôle — l'étiquette (`htmlFor`), le clavier,
 * `required`, `accept`, `ref` et `onChange` le visent. Il couvre tout le
 * champ, transparent, par-dessus ce qui se voit : un fichier glissé depuis
 * l'explorateur y tombe encore (masqué en `sr-only`, il ne recevait plus
 * rien, et le navigateur ouvrait le fichier à la place de la page).
 *
 * Le nom du fichier choisi — ou « Aucun fichier choisi » — décrit le champ
 * (`aria-describedby`) : sans cela, un lecteur d'écran annonçait la valeur
 * native, dans la langue du navigateur. Le champ natif étant au-dessus de
 * tout, c'est lui qui porte l'infobulle (`title`) : un nom long, tronqué à
 * l'écran, se lit en entier au survol, et l'infobulle native ne parle plus
 * la langue du navigateur.
 *
 * Désactivé ou invalide (`aria-invalid`), il s'affiche comme `<Input>`.
 */
function ChampFichier({
  className,
  onChange,
  ref,
  title,
  "aria-describedby": decritPar,
  ...props
}: Omit<React.ComponentProps<"input">, "type">) {
  const { t } = useTranslation()
  const [nom, setNom] = React.useState<string | null>(null)
  const idDuNom = React.useId()
  const affiche = nom ?? t("commun.fichier.aucun")

  return (
    <label
      className={cn(
        "relative flex h-8 w-full min-w-0 cursor-pointer items-center gap-2 rounded-lg border border-input bg-transparent px-1 text-sm transition-colors",
        "has-[input:focus-visible]:border-ring has-[input:focus-visible]:ring-3 has-[input:focus-visible]:ring-ring/50",
        "has-[input:disabled]:cursor-not-allowed has-[input:disabled]:bg-input/50 has-[input:disabled]:opacity-50 dark:bg-input/30 dark:has-[input:disabled]:bg-input/80",
        "has-[input[aria-invalid=true]]:border-destructive has-[input[aria-invalid=true]]:ring-3 has-[input[aria-invalid=true]]:ring-destructive/20 dark:has-[input[aria-invalid=true]]:border-destructive/50 dark:has-[input[aria-invalid=true]]:ring-destructive/40",
        className,
      )}
    >
      <input
        {...props}
        ref={ref}
        type="file"
        title={title ?? affiche}
        aria-describedby={decritPar ? `${idDuNom} ${decritPar}` : idDuNom}
        className="absolute inset-0 h-full w-full cursor-pointer opacity-0 disabled:cursor-not-allowed"
        onChange={(event) => {
          setNom(event.target.files?.[0]?.name ?? null)
          onChange?.(event)
        }}
      />
      <span
        aria-hidden
        className="inline-flex h-6 shrink-0 items-center gap-1.5 rounded-md border border-border bg-muted px-2 text-xs font-medium text-foreground"
      >
        <Upload className="h-3.5 w-3.5" />
        {t("commun.fichier.choisir")}
      </span>
      {/* Caché aux lecteurs d'écran mais référencé par `aria-describedby`,
          qui le lit quand même : visible, il entrerait aussi dans le nom du
          champ par l'étiquette qui l'enveloppe (« Fichier Aucun fichier
          choisi »), annoncé deux fois. Pas d'infobulle ici : le champ
          natif le couvre, il n'est jamais survolé ; c'est le champ qui
          porte le nom entier (`title`). */}
      <span
        id={idDuNom}
        aria-hidden
        className={cn("truncate", nom ? "text-foreground" : "text-muted-foreground")}
      >
        {affiche}
      </span>
    </label>
  )
}

export { ChampFichier }
