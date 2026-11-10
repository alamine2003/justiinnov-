import type { ComponentType } from "react"
import { useSearchParams } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { PageHeader } from "@/components/ui/page-header"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { CountriesSection } from "@/pages/configuration/countries-section"
import { UsersSection } from "@/pages/configuration/users-section"
import { GeneralSection } from "@/pages/configuration/general-section"
import { PermissionsSection } from "@/pages/configuration/permissions-section"
import { ProjectTypesSection } from "@/pages/configuration/project-types-section"

/**
 * Le registre des sections, dans l'ordre des onglets : une section s'ajoute
 * ici, une seule fois, et son onglet comme son contenu en découlent.
 *
 * L'identifiant d'onglet est une valeur technique, reprise dans l'URL
 * (`?onglet=utilisateurs`) ; seul son libellé est traduit
 * (`configuration.onglets.<onglet>`).
 */
const SECTIONS = [
  { onglet: "general", Section: GeneralSection },
  { onglet: "utilisateurs", Section: UsersSection },
  { onglet: "pays", Section: CountriesSection },
  { onglet: "types-de-projets", Section: ProjectTypesSection },
  { onglet: "permissions", Section: PermissionsSection },
] as const satisfies readonly { onglet: string; Section: ComponentType }[]

type Onglet = (typeof SECTIONS)[number]["onglet"]

const ONGLETS: readonly string[] = SECTIONS.map((section) => section.onglet)

export function ConfigurationPage() {
  const { t } = useTranslation()
  // L'onglet vit dans l'URL : un lien vers « Configuration › Permissions »
  // doit rouvrir cet onglet, pas le premier.
  const [params, setParams] = useSearchParams()
  // L'import a quitté la configuration pour les dossiers : c'est une
  // déclaration, qui revient au pays (décision 89).
  // Une valeur inconnue — `?onglet=xyz`, ou l'ancien `?onglet=import` —
  // laissait une barre d'onglets sans onglet actif et aucun contenu : une
  // page blanche sans explication.
  // « Types de dossiers » est devenu « Types de projets » (décision 119) :
  // un lien enregistré vers l'ancien onglet ouvre le nouveau, qui les porte.
  const brut = params.get("onglet")
  const demande = brut === "types-de-dossiers" ? "types-de-projets" : brut
  const onglet: Onglet = demande && ONGLETS.includes(demande) ? (demande as Onglet) : "general"

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
          {SECTIONS.map(({ onglet: valeur }) => (
            <TabsTrigger key={valeur} value={valeur}>
              {t(`configuration.onglets.${valeur}`)}
            </TabsTrigger>
          ))}
        </TabsList>

        {SECTIONS.map(({ onglet: valeur, Section }) => (
          <TabsContent
            key={valeur}
            value={valeur}
            className="defile -mx-1 mt-4 px-1 pb-1 court:mt-2"
          >
            <Section />
          </TabsContent>
        ))}
      </Tabs>
    </div>
  )
}
