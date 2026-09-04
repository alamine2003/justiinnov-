import { Link, useParams } from "react-router-dom"
import { AlertTriangle, ArrowLeft, Loader2 } from "lucide-react"
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
import { invalidateReferentiel } from "@/lib/referentiel"
import { STATUS_TONES } from "@/lib/status-styles"
import { PROJECT_STATUS_LABELS, type CountryDetail } from "@/lib/types"
import { useQuery } from "@/lib/use-query"
import { formatAmount, normalizeDecimal } from "@/lib/utils"

const PROJECT_STATUS_OPTIONS = Object.entries(PROJECT_STATUS_LABELS).map(([value, label]) => ({
  value,
  label,
}))

function ActiveBadge({ active, feminine = false }: { active: boolean; feminine?: boolean }) {
  return active ? (
    <Badge className={STATUS_TONES.SUCCES}>{feminine ? "Active" : "Actif"}</Badge>
  ) : (
    <Badge variant="secondary">{feminine ? "Inactive" : "Inactif"}</Badge>
  )
}

export function CountryDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { can } = useAuth()
  const canManage = can("manage_subentities")
  const countryId = Number(id)

  const query = useQuery(
    `country:detail:${countryId}`,
    (signal) => fetchCountry(countryId, signal),
    { fallback: "Impossible de charger le pays" },
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
        <span className="sr-only">Chargement du pays…</span>
      </div>
    )
  }

  if (!country) {
    return (
      <div className="space-y-4">
        <BackLink />
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Pays introuvable</AlertTitle>
          <AlertDescription>{query.error ?? "Ce pays n'existe pas ou n'est pas dans votre périmètre."}</AlertDescription>
        </Alert>
      </div>
    )
  }

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
      throw new Error("Le budget doit être un nombre.")
    }
    return { ...data, budget: normalise }
  })
  const saveExpense = saver(createExpenseTitle, updateExpenseTitle)
  const saveCategory = saver(createMarketingCategory, updateMarketingCategory)

  return (
    <div className="space-y-6">
      <BackLink />

      {query.error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Erreur</AlertTitle>
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
                <Loader2 className="ml-2 inline h-3.5 w-3.5 animate-spin align-middle" aria-label="Actualisation" />
              )}
            </>
          }
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Équipes" value={country.team_count} />
        <StatCard label="Centres de coûts" value={country.cost_center_count} />
        <StatCard label="Projets" value={country.project_count} />
        <StatCard label="Intitulés de dépenses" value={country.expense_title_count} />
      </div>

      <Tabs defaultValue="equipes">
        <TabsList className="flex w-full flex-wrap justify-start overflow-x-auto bg-muted/60">
          <TabsTrigger value="managers">Manager(s)</TabsTrigger>
          <TabsTrigger value="equipes">Équipes</TabsTrigger>
          <TabsTrigger value="costs">Centres de coûts</TabsTrigger>
          <TabsTrigger value="projets">Projets</TabsTrigger>
          <TabsTrigger value="depenses">Intitulés de dépenses</TabsTrigger>
          <TabsTrigger value="marketing">Catégories marketing</TabsTrigger>
          <TabsTrigger value="beneficiaires">Bénéficiaires</TabsTrigger>
          <TabsTrigger value="historique">Historique</TabsTrigger>
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
                title="Équipes"
                description="Équipes rattachées à ce pays."
                rows={country.teams}
                columns={[
                  { key: "name", header: "Nom" },
                  {
                    key: "is_active",
                    header: "Statut",
                    render: (t) => <ActiveBadge active={t.is_active} feminine />,
                  },
                ]}
                detectActive={(t) => t.is_active}
                defaultForm={{ name: "" }}
                formFields={[{ key: "name", label: "Nom", placeholder: "Équipe commerciale" }]}
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
                title="Centres de coûts"
                rows={country.cost_centers}
                columns={[
                  { key: "code", header: "Code" },
                  { key: "name", header: "Libellé" },
                  {
                    key: "is_active",
                    header: "Statut",
                    render: (c) => <ActiveBadge active={c.is_active} />,
                  },
                ]}
                detectActive={(c) => c.is_active}
                defaultForm={{ code: "", name: "" }}
                formFields={[
                  { key: "code", label: "Code", placeholder: "CC01" },
                  { key: "name", label: "Libellé", placeholder: "Centre Paris" },
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
                title="Projets"
                rows={country.projects}
                columns={[
                  { key: "name", header: "Nom" },
                  {
                    key: "status",
                    header: "Statut",
                    render: (p) => <ProjectStatusBadge status={p.status} />,
                  },
                  {
                    key: "budget",
                    header: "Budget",
                    render: (p) =>
                      p.budget ? (
                        formatAmount(p.budget, country.currency_symbol || country.currency)
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      ),
                  },
                ]}
                detectActive={(p) => p.is_active}
                defaultForm={{ name: "", status: "planned", budget: "" }}
                formFields={[
                  { key: "name", label: "Nom", placeholder: "Projet 2026" },
                  { key: "status", label: "Statut", options: PROJECT_STATUS_OPTIONS },
                  {
                    key: "budget",
                    label: `Budget (${country.currency_symbol || country.currency})`,
                    placeholder: "0",
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
                title="Intitulés de dépenses"
                rows={country.expense_titles}
                columns={[
                  { key: "label", header: "Intitulé" },
                  { key: "description", header: "Description" },
                  {
                    key: "is_active",
                    header: "Statut",
                    render: (e) => <ActiveBadge active={e.is_active} />,
                  },
                ]}
                detectActive={(e) => e.is_active}
                defaultForm={{ label: "", description: "" }}
                formFields={[
                  { key: "label", label: "Intitulé", placeholder: "Frais de déplacement" },
                  { key: "description", label: "Description", optional: true },
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
                title="Catégories marketing"
                rows={country.marketing_categories}
                columns={[
                  { key: "name", header: "Nom" },
                  { key: "description", header: "Description" },
                  {
                    key: "is_active",
                    header: "Statut",
                    render: (m) => <ActiveBadge active={m.is_active} feminine />,
                  },
                ]}
                detectActive={(m) => m.is_active}
                defaultForm={{ name: "", description: "" }}
                formFields={[
                  { key: "name", label: "Nom", placeholder: "Marketing digital" },
                  { key: "description", label: "Description", optional: true },
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
  return (
    <div className="flex">
      <Link
        to="/countries"
        className="inline-flex items-center rounded text-sm text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <ArrowLeft className="mr-2 h-4 w-4" aria-hidden />
        Retour aux pays
      </Link>
    </div>
  )
}
