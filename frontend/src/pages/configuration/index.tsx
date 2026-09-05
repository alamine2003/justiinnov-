import { useSearchParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { PageHeader } from "@/components/ui/page-header"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useAuth } from "@/context/use-auth"
import { CountriesSection } from "@/pages/configuration/countries-section"
import { ImportSection } from "@/pages/configuration/import-section"
import { UsersSection } from "@/pages/configuration/users-section"
import { GeneralSection } from "@/pages/configuration/general-section"
import { PermissionsSection } from "@/pages/configuration/permissions-section"

/**
 * Identifiants d'onglets : valeurs techniques, reprises dans l'URL
 * (`?onglet=utilisateurs`). Seuls les libellés sont traduits.
 */
const ONGLETS = ["general", "utilisateurs", "pays", "permissions", "import"] as const

export function ConfigurationPage() {
  const { t } = useTranslation()
  const { can } = useAuth()
  // L'onglet vit dans l'URL : un lien vers « Configuration › Permissions »
  // doit rouvrir cet onglet, pas le premier.
  const [params, setParams] = useSearchParams()
  const onglet = params.get("onglet") ?? "general"
  // L'import manipule des fichiers : réservé aux administrateurs par défaut
  // (`data.import`).
  const onglets = ONGLETS.filter((value) => value !== "import" || can("data.import"))

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("configuration.titre")}
        description={t("configuration.description")}
      />

      <Tabs
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

        <TabsContent value="general" className="mt-4">
          <GeneralSection />
        </TabsContent>
        <TabsContent value="utilisateurs" className="mt-4">
          <UsersSection />
        </TabsContent>
        <TabsContent value="pays" className="mt-4">
          <CountriesSection />
        </TabsContent>
        <TabsContent value="permissions" className="mt-4">
          <PermissionsSection />
        </TabsContent>
        {can("data.import") && (
          <TabsContent value="import" className="mt-4">
            <ImportSection />
          </TabsContent>
        )}
      </Tabs>
    </div>
  )
}
