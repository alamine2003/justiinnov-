import { Link, useParams } from "react-router-dom"
import { AlertTriangle, ArrowLeft, Loader2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { PageHeader } from "@/components/ui/page-header"
import { StatCard } from "@/components/ui/stat-card"
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs"
import { ManageRows } from "@/components/countries/manage-rows"
import { ManageBeneficiaries } from "@/components/countries/manage-beneficiaries"
import { ManageManagers } from "@/components/countries/manage-managers"
import { CaretHistory } from "@/components/countries/history"
import { ProjectStatusBadge } from "@/components/expenses/status-badge"
import {
  createCostCenter,
  createExpenseTitle,
  createMarketingCategory,
  createProject,
  createTeam,
  fetchCountry,
  updateCostCenter,
  updateExpenseTitle,
  updateMarketingCategory,
  updateProject,
  updateTeam,
} from "@/lib/countries"
import { useAuth } from "@/context/use-auth"
import { PROJECT_STATUSES, projectStatusLabel } from "@/lib/labels"
import { invalidateReferentiel } from "@/lib/referentiel"
import { STATUS_TONES } from "@/lib/status-styles"
import type { CountryDetail } from "@/lib/types"
import { useQuery } from "@/lib/use-query"
import { formatAmount, normalizeDecimal } from "@/lib/utils"

function ActiveBadge({ active, feminine = false }: { active: boolean; feminine?: boolean }) {
  const { t } = useTranslation()
  return active ? (
    <Badge className={STATUS_TONES.SUCCES}>
      {feminine ? t("pays.statut.active") : t("pays.statut.actif")}
    </Badge>
  ) : (
    <Badge variant="secondary">
      {feminine ? t("pays.statut.inactive") : t("pays.statut.inactif")}
    </Badge>
  )
}

export function CountryDetailPage() {
  const { t } = useTranslation()
  const { id } = useParams<{ id: string }>()
  const { can } = useAuth()
  const canManage = can("manage_subentities")
  const countryId = Number(id)

  const query = useQuery(
    `country:detail:${countryId}`,
    (signal) => fetchCountry(countryId, signal),
    { fallback: t("pays.fiche.chargement_impossible") },
  )
  const country = query.data

  // Toute écriture invalide la copie que le formulaire de dépense garde en
  // cache, puis relit la fiche.
  const refresh = async () => {
    invalidateReferentiel(`country:${countryId}`)
    invalidateReferentiel("countries")
    invalidateReferentiel("teams")
    invalidateReferentiel("projects")
    invalidateReferentiel("managers")
    query.reload()
  }

  if (query.loading && !country) {
    return (
      <div className="flex h-64 items-center justify-center" aria-busy="true">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        <span className="sr-only">{t("pays.fiche.chargement")}</span>
      </div>
    )
  }

  if (!country) {
    return (
      <div className="space-y-4">
        <BackLink />
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("pays.fiche.introuvable_titre")}</AlertTitle>
          <AlertDescription>{query.error ?? t("pays.fiche.introuvable_texte")}</AlertDescription>
        </Alert>
      </div>
    )
  }

  const statutOptions = PROJECT_STATUSES.map((value) => ({
    value,
    label: projectStatusLabel(t, value),
  }))

  const saver =
    (
      create: (data: Record<string, unknown>) => Promise<unknown>,
      update: (id: number, data: Record<string, unknown>) => Promise<unknown>,
      transform: (data: Record<string, unknown>) => Record<string, unknown> = (d) => d,
    ) =>
    async (data: Record<string, unknown>, itemId?: number) => {
      const payload = { country: countryId, ...transform(data) }
      if (itemId) await update(itemId, payload)
      else await create(payload)
      await refresh()
    }

  const saveTeam = saver(createTeam, updateTeam)
  const saveCostCenter = saver(createCostCenter, updateCostCenter)
  const saveProject = saver(createProject, updateProject, (data) => {
    // Le budget d'un projet est facultatif ; vide, il est explicitement nul
    // plutôt qu'une chaîne que le serveur refuserait.
    const budget = typeof data.budget === "string" ? data.budget.trim() : ""
    const normalise = budget ? normalizeDecimal(budget) : null
    if (budget && normalise === null) {
      throw new Error(t("pays.fiche.budget_nombre"))
    }
    return { ...data, budget: normalise }
  })
  const saveExpense = saver(createExpenseTitle, updateExpenseTitle)
  const saveCategory = saver(createMarketingCategory, updateMarketingCategory)

  const devise = country.currency_symbol || country.currency

  return (
    <div className="space-y-6">
      <BackLink />

      {query.error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("commun.erreur")}</AlertTitle>
          <AlertDescription>{query.error}</AlertDescription>
        </Alert>
      )}

      <div className="flex items-start gap-4">
        <div
          aria-hidden
          className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-primary text-lg font-semibold uppercase text-primary-foreground shadow-lg shadow-primary/15"
        >
          {country.code}
        </div>
        <PageHeader
          title={country.name}
          description={
            <>
              <span className="mr-2 inline-flex align-middle">
                <ActiveBadge active={country.is_active} />
              </span>
              {country.currency_symbol} {country.currency} · {country.timezone}
              {query.refreshing && (
                <Loader2
                  className="ml-2 inline h-3.5 w-3.5 animate-spin align-middle"
                  aria-label={t("pays.fiche.actualisation")}
                />
              )}
            </>
          }
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label={t("pays.fiche.equipes")} value={country.team_count} />
        <StatCard label={t("pays.fiche.centres_couts")} value={country.cost_center_count} />
        <StatCard label={t("pays.fiche.projets")} value={country.project_count} />
        <StatCard label={t("pays.fiche.intitules_depenses")} value={country.expense_title_count} />
      </div>

      <Tabs defaultValue="equipes">
        <TabsList className="flex w-full flex-wrap justify-start overflow-x-auto bg-muted/60">
          <TabsTrigger value="managers">{t("pays.fiche.managers")}</TabsTrigger>
          <TabsTrigger value="equipes">{t("pays.fiche.equipes")}</TabsTrigger>
          <TabsTrigger value="costs">{t("pays.fiche.centres_couts")}</TabsTrigger>
          <TabsTrigger value="projets">{t("pays.fiche.projets")}</TabsTrigger>
          <TabsTrigger value="depenses">{t("pays.fiche.intitules_depenses")}</TabsTrigger>
          <TabsTrigger value="marketing">{t("pays.fiche.categories_marketing")}</TabsTrigger>
          <TabsTrigger value="beneficiaires">{t("pays.fiche.beneficiaires")}</TabsTrigger>
          <TabsTrigger value="historique">{t("pays.fiche.historique")}</TabsTrigger>
        </TabsList>

        <TabsContent value="managers" className="mt-4">
          <Card className="border-border/60 shadow-sm">
            <CardContent className="pt-6">
              <ManageManagers
                countryId={countryId}
                managers={country.managers}
                onRefresh={refresh}
                canManage={can("manage_countries")}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="equipes" className="mt-4">
          <Card className="border-border/60 shadow-sm">
            <CardContent className="pt-6">
              <ManageRows<CountryDetail["teams"][number]>
                title={t("pays.fiche.equipes")}
                description={t("pays.equipes.description")}
                rows={country.teams}
                columns={[
                  { key: "name", header: t("champs.name") },
                  {
                    key: "is_active",
                    header: t("commun.statut"),
                    render: (equipe) => <ActiveBadge active={equipe.is_active} feminine />,
                  },
                ]}
                detectActive={(equipe) => equipe.is_active}
                defaultForm={{ name: "" }}
                formFields={[
                  {
                    key: "name",
                    label: t("champs.name"),
                    placeholder: t("pays.equipes.nom_placeholder"),
                  },
                ]}
                canManage={canManage}
                onSave={saveTeam}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="costs" className="mt-4">
          <Card className="border-border/60 shadow-sm">
            <CardContent className="pt-6">
              <ManageRows<CountryDetail["cost_centers"][number]>
                title={t("pays.fiche.centres_couts")}
                rows={country.cost_centers}
                columns={[
                  { key: "code", header: t("champs.code") },
                  { key: "name", header: t("champs.label") },
                  {
                    key: "is_active",
                    header: t("commun.statut"),
                    render: (c) => <ActiveBadge active={c.is_active} />,
                  },
                ]}
                detectActive={(c) => c.is_active}
                defaultForm={{ code: "", name: "" }}
                formFields={[
                  {
                    key: "code",
                    label: t("champs.code"),
                    placeholder: t("pays.centres_couts.code_placeholder"),
                  },
                  {
                    key: "name",
                    label: t("champs.label"),
                    placeholder: t("pays.centres_couts.libelle_placeholder"),
                  },
                ]}
                canManage={canManage}
                onSave={saveCostCenter}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="projets" className="mt-4">
          <Card className="border-border/60 shadow-sm">
            <CardContent className="pt-6">
              <ManageRows<CountryDetail["projects"][number]>
                title={t("pays.fiche.projets")}
                rows={country.projects}
                columns={[
                  { key: "name", header: t("champs.name") },
                  {
                    key: "status",
                    header: t("commun.statut"),
                    render: (p) => <ProjectStatusBadge status={p.status} />,
                  },
                  {
                    key: "budget",
                    header: t("pays.fiche.budget"),
                    render: (p) =>
                      p.budget ? (
                        formatAmount(p.budget, devise)
                      ) : (
                        <span className="text-muted-foreground">{t("commun.aucun")}</span>
                      ),
                  },
                ]}
                detectActive={(p) => p.is_active}
                defaultForm={{ name: "", status: "planned", budget: "" }}
                formFields={[
                  {
                    key: "name",
                    label: t("champs.name"),
                    placeholder: t("pays.projets.nom_placeholder"),
                  },
                  { key: "status", label: t("commun.statut"), options: statutOptions },
                  {
                    key: "budget",
                    label: t("pays.fiche.budget_devise", { devise }),
                    placeholder: t("pays.projets.budget_placeholder"),
                    optional: true,
                    decimal: true,
                  },
                ]}
                canManage={canManage}
                onSave={saveProject}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="depenses" className="mt-4">
          <Card className="border-border/60 shadow-sm">
            <CardContent className="pt-6">
              <ManageRows<CountryDetail["expense_titles"][number]>
                title={t("pays.fiche.intitules_depenses")}
                rows={country.expense_titles}
                columns={[
                  { key: "label", header: t("champs.expense_title") },
                  { key: "description", header: t("commun.description") },
                  {
                    key: "is_active",
                    header: t("commun.statut"),
                    render: (e) => <ActiveBadge active={e.is_active} />,
                  },
                ]}
                detectActive={(e) => e.is_active}
                defaultForm={{ label: "", description: "" }}
                formFields={[
                  {
                    key: "label",
                    label: t("champs.expense_title"),
                    placeholder: t("pays.depenses.intitule_placeholder"),
                  },
                  { key: "description", label: t("commun.description"), optional: true },
                ]}
                canManage={canManage}
                onSave={saveExpense}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="marketing" className="mt-4">
          <Card className="border-border/60 shadow-sm">
            <CardContent className="pt-6">
              <ManageRows<CountryDetail["marketing_categories"][number]>
                title={t("pays.fiche.categories_marketing")}
                rows={country.marketing_categories}
                columns={[
                  { key: "name", header: t("champs.name") },
                  { key: "description", header: t("commun.description") },
                  {
                    key: "is_active",
                    header: t("commun.statut"),
                    render: (m) => <ActiveBadge active={m.is_active} feminine />,
                  },
                ]}
                detectActive={(m) => m.is_active}
                defaultForm={{ name: "", description: "" }}
                formFields={[
                  {
                    key: "name",
                    label: t("champs.name"),
                    placeholder: t("pays.marketing.nom_placeholder"),
                  },
                  { key: "description", label: t("commun.description"), optional: true },
                ]}
                canManage={canManage}
                onSave={saveCategory}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="beneficiaires" className="mt-4">
          <Card className="border-border/60 shadow-sm">
            <CardContent className="pt-6">
              <ManageBeneficiaries countryId={countryId} canManage={canManage} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="historique" className="mt-4">
          <CaretHistory countryId={countryId} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function BackLink() {
  const { t } = useTranslation()
  return (
    <div className="flex">
      <Link
        to="/countries"
        className="inline-flex items-center rounded text-sm text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <ArrowLeft className="mr-2 h-4 w-4" aria-hidden />
        {t("pays.fiche.retour")}
      </Link>
    </div>
  )
}
