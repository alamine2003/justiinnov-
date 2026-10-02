import { useTranslation } from "react-i18next"
import { PageHeader } from "@/components/ui/page-header"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { JournalDuCircuit } from "./circuit"
import { useFiltresAudit } from "./use-filtres"
import { VueDEnsemble } from "./overview"
import { JournalDuReferentiel } from "./referentiel"

/**
 * Identifiants d'onglets : valeurs techniques, reprises dans l'URL
 * (`?onglet=circuit`). Seuls les libellés sont traduits.
 */
const ONGLETS = ["vue", "circuit", "referentiel"] as const
type Onglet = (typeof ONGLETS)[number]

/**
 * L'audit en tableau de bord (décision 111), pour la RH et la direction
 * (`audit.read`) : une vue d'ensemble comptée par le serveur, puis les deux
 * journaux — le circuit (`AuditLog`) et le référentiel, les comptes et la
 * configuration (`ChangeLog`) —, tous filtrables par période et par pays.
 * Rien ne se modifie ni ne se supprime ici.
 */
export function AuditPage() {
  const { t } = useTranslation()
  const { lire, changer } = useFiltresAudit()
  const demande = lire("onglet")
  const onglet: Onglet = ONGLETS.includes(demande as Onglet) ? (demande as Onglet) : "vue"

  // Changer d'onglet garde la période et le pays, pas les filtres propres
  // à l'onglet quitté.
  const changeOnglet = (value: string) =>
    changer({
      onglet: value === "vue" ? "" : value,
      page: "",
      action: "",
      object_type: "",
      model_name: "",
      user: "",
      projet: "",
      search: "",
    })

  return (
    <div className="space-y-6">
      <PageHeader title={t("audit.titre")} description={t("audit.description")} />

      <Tabs value={onglet} onValueChange={(value) => changeOnglet(String(value))}>
        <TabsList
          variant="line"
          aria-label={t("audit.onglets.aria")}
          className="w-full flex-wrap justify-start border-b border-border/60 group-data-horizontal/tabs:h-auto"
        >
          {ONGLETS.map((value) => (
            <TabsTrigger key={value} value={value} className="flex-none px-3 py-1.5">
              {t(`audit.onglets.${value}`)}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="vue" className="mt-4">
          {onglet === "vue" && <VueDEnsemble />}
        </TabsContent>
        <TabsContent value="circuit" className="mt-4">
          {onglet === "circuit" && <JournalDuCircuit />}
        </TabsContent>
        <TabsContent value="referentiel" className="mt-4">
          {onglet === "referentiel" && <JournalDuReferentiel />}
        </TabsContent>
      </Tabs>
    </div>
  )
}
