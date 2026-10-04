import { useSearchParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { PageHeader } from "@/components/ui/page-header"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { CountriesSection } from "@/pages/configuration/countries-section"
import { UsersSection } from "@/pages/configuration/users-section"
import { GeneralSection } from "@/pages/configuration/general-section"
import { PermissionsSection } from "@/pages/configuration/permissions-section"
import { DossierKindsSection } from "@/pages/configuration/dossier-kinds-section"

/**
 * Identifiants d'onglets : valeurs techniques, reprises dans l'URL
 * (`?onglet=utilisateurs`). Seuls les libellés sont traduits.
 */
const ONGLETS = ["general", "utilisateurs", "pays", "types-de-dossiers", "permissions"] as const

type Onglet = (typeof ONGLETS)[number]

export function ConfigurationPage() {
  const { t } = useTranslation()
  // L'onglet vit dans l'URL : un lien vers « Configuration › Permissions »
  // doit rouvrir cet onglet, pas le premier.
  const [params, setParams] = useSearchParams()
  // L'import a quitté la configuration pour les dossiers : c'est une
  // déclaration, qui revient au pays (décision 89).
  const onglets = ONGLETS
  // Une valeur inconnue — `?onglet=xyz`, ou l'ancien `?onglet=import` —
  // laissait une barre d'onglets sans onglet actif et aucun contenu : une
  // page blanche sans explication.
  const demande = params.get("onglet")
  const onglet = demande && onglets.includes(demande as Onglet) ? demande : "general"

  return (
    <div className="ecran-plein space-y-6 court:space-y-3">
      <PageHeader
        title={t("configuration.titre")}
        description={t("configuration.description")}
      />

      {/* Dès `lg`, les onglets restent en vue et la section défile
          dessous (DESIGN.md, « Hauteur d'écran »). */}
      <Tabs
        className="remplit"
        value={onglet}
        onValueChange={(value) => setParams({ onglet: value })}
      >
        <TabsList className="flex w-full flex-wrap justify-start bg-muted/60">
          {onglets.map((value) => (
            <TabsTrigger key={value} value={value}>
              {t(`configuration.onglets.${value}`)}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="general" className="defile -mx-1 mt-4 px-1 pb-1 court:mt-2">
          <GeneralSection />
        </TabsContent>
        <TabsContent value="utilisateurs" className="defile -mx-1 mt-4 px-1 pb-1 court:mt-2">
          <UsersSection />
        </TabsContent>
        <TabsContent value="pays" className="defile -mx-1 mt-4 px-1 pb-1 court:mt-2">
          <CountriesSection />
        </TabsContent>
        <TabsContent value="types-de-dossiers" className="defile -mx-1 mt-4 px-1 pb-1 court:mt-2">
          <DossierKindsSection />
        </TabsContent>
        <TabsContent value="permissions" className="defile -mx-1 mt-4 px-1 pb-1 court:mt-2">
          <PermissionsSection />
        </TabsContent>
      </Tabs>
    </div>
  )
}
