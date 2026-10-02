import { useTranslation } from "react-i18next"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { ParPays } from "@/lib/types"

/** Valeur de l'onglet « Tous les pays » : base-ui ne distingue pas un onglet de valeur vide. */
const TOUS_LES_PAYS = "tous"

/**
 * Onglets par pays d'une liste — dossiers, projets (décision 99).
 *
 * « Tous les pays », puis un onglet par pays du périmètre, chacun suivi du
 * nombre d'objets qu'il affichera : le serveur les compte
 * (`…/par-pays/`), l'interface n'additionne rien. Les onglets passent à la
 * ligne quand les dix-sept filiales sont ouvertes, jamais une barre qui
 * défile. `onChange` reçoit l'identifiant du pays, ou `""` pour tous.
 */
export function CountryTabs({
  value,
  onChange,
  data,
  label,
}: {
  value: number | ""
  onChange: (value: string) => void
  data: ParPays | null
  /** Ce que les onglets filtrent, pour les lecteurs d'écran. */
  label: string
}) {
  const { t } = useTranslation()
  return (
    <Tabs
      value={value === "" ? TOUS_LES_PAYS : String(value)}
      onValueChange={(choix) => onChange(choix === TOUS_LES_PAYS ? "" : String(choix))}
    >
      <TabsList
        variant="line"
        aria-label={label}
        className="w-full flex-wrap justify-start border-b border-border/60 group-data-horizontal/tabs:h-auto"
      >
        <TabsTrigger value={TOUS_LES_PAYS} className="flex-none px-3 py-1.5">
          {t("dossiers.liste.tous_pays")}{" "}
          <CompteOnglet valeur={data?.total} />
        </TabsTrigger>
        {(data?.pays ?? []).map((pays) => (
          <TabsTrigger key={pays.id} value={String(pays.id)} className="flex-none px-3 py-1.5">
            {pays.name}{" "}
            <CompteOnglet valeur={pays.count} />
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  )
}

/**
 * Nombre d'objets d'un onglet, tel que le serveur l'a compté. L'espace qui
 * le précède est pour les lecteurs d'écran : sans lui, l'onglet
 * s'annonçait « Togo2 ».
 */
function CompteOnglet({ valeur }: { valeur: number | undefined }) {
  if (valeur === undefined) return null
  return <span className="text-xs tabular-nums text-muted-foreground">{valeur}</span>
}
