import { useCallback, useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { ArrowLeft, Loader2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
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
import { useAuth } from "@/context/auth"
import type { CountryDetail } from "@/lib/types"

export function CountryDetailPage() {
  const { id } = useParams<{ id: string }>()
  const { can } = useAuth()
  const canManage = can("manage_subentities")
  const countryId = Number(id)
  const [country, setCountry] = useState<CountryDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState("equipes")

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await fetchCountry(countryId)
      setCountry(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Impossible de charger le pays")
    } finally {
      setLoading(false)
    }
  }, [countryId])

  useEffect(() => {
    load()
  }, [load])

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (error || !country) {
    return (
      <div className="space-y-4">
        <Link
          to="/countries"
          className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Retour
        </Link>
        <p className="text-muted-foreground">{error ?? "Pays introuvable."}</p>
      </div>
    )
  }

  const saveTeam = async (data: Record<string, unknown>, itemId?: number) => {
    const payload = { country: countryId, ...data }
    if (itemId) await updateTeam(itemId, payload as Record<string, unknown>)
    else await createTeam(payload as Record<string, unknown>)
    await load()
  }

  const saveCostCenter = async (data: Record<string, unknown>, itemId?: number) => {
    const payload = { country: countryId, ...data }
    if (itemId) await updateCostCenter(itemId, payload as Record<string, unknown>)
    else await createCostCenter(payload as Record<string, unknown>)
    await load()
  }

  const saveProject = async (data: Record<string, unknown>, itemId?: number) => {
    const payload = { country: countryId, ...data }
    if (itemId) await updateProject(itemId, payload as Record<string, unknown>)
    else await createProject(payload as Record<string, unknown>)
    await load()
  }

  const saveExpense = async (data: Record<string, unknown>, itemId?: number) => {
    const payload = { country: countryId, ...data }
    if (itemId) await updateExpenseTitle(itemId, payload as Record<string, unknown>)
    else await createExpenseTitle(payload as Record<string, unknown>)
    await load()
  }

  const saveCategory = async (data: Record<string, unknown>, itemId?: number) => {
    const payload = { country: countryId, ...data }
    if (itemId) await updateMarketingCategory(itemId, payload as Record<string, unknown>)
    else await createMarketingCategory(payload as Record<string, unknown>)
    await load()
  }

  return (
    <div className="space-y-6">
      <div className="flex">
        <Link
          to="/countries"
          className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="mr-2 h-4 w-4" />
          Retour
        </Link>
      </div>

      <div className="flex items-center gap-4">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-primary text-lg font-semibold text-primary-foreground shadow-lg shadow-primary/15 uppercase">
          {country.code}
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{country.name}</h1>
            {country.is_active ? (
              <Badge className="bg-emerald-500/90 shadow-sm shadow-emerald-500/20 hover:bg-emerald-500">Actif</Badge>
            ) : (
              <Badge variant="secondary">Inactif</Badge>
            )}
          </div>
          <p className="text-sm text-muted-foreground">
            {country.currency_symbol} {country.currency} · {country.timezone}
          </p>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Équipes" value={country.team_count} />
        <StatCard label="Centres de coûts" value={country.cost_center_count} />
        <StatCard label="Projets" value={country.project_count} />
        <StatCard label="Intitulés de dépenses" value={country.expense_title_count} />
      </div>

      <Tabs value={tab} onValueChange={setTab}>
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
                onRefresh={load}
                canManage={can("manage_countries")}
              />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="equipes" className="mt-4">
          <Card className="border-border/60 shadow-sm">
            <CardContent className="pt-6">
              <ManageRows
                title="Équipes"
                description="Équipes rattachées à ce pays."
                rows={country.teams}
                loading={loading}
                columns={[
                  { key: "name", header: "Nom" },
                  {
                    key: "is_active",
                    header: "Statut",
                    render: (t) =>
                      t.is_active ? (
                        <Badge className="bg-emerald-500 hover:bg-emerald-500">Active</Badge>
                      ) : (
                        <Badge variant="secondary">Inactive</Badge>
                      ),
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
              <ManageRows
                title="Centres de coûts"
                rows={country.cost_centers}
                loading={loading}
                columns={[
                  { key: "code", header: "Code" },
                  { key: "name", header: "Libellé" },
                  {
                    key: "is_active",
                    header: "Statut",
                    render: (c) =>
                      c.is_active ? (
                        <Badge className="bg-emerald-500 hover:bg-emerald-500">Actif</Badge>
                      ) : (
                        <Badge variant="secondary">Inactif</Badge>
                      ),
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
              <ManageRows
                title="Projets"
                rows={country.projects}
                loading={loading}
                columns={[
                  { key: "name", header: "Nom" },
                  {
                    key: "status",
                    header: "Statut",
                    render: (p) => <StatusBadge value={p.status} />,
                  },
                  {
                    key: "budget",
                    header: "Budget",
                    render: (p) =>
                      p.budget ? (
                        `${country.currency_symbol} ${Number(p.budget).toLocaleString("fr-FR")}`
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      ),
                  },
                ]}
                detectActive={(p) => p.is_active}
                defaultForm={{ name: "", status: "planned", budget: "" }}
                formFields={[
                  { key: "name", label: "Nom", placeholder: "Projet 2026" },
                  { key: "budget", label: "Budget", placeholder: "0" },
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
              <ManageRows
                title="Intitulés de dépenses"
                rows={country.expense_titles}
                loading={loading}
                columns={[
                  { key: "label", header: "Intitulé" },
                  { key: "description", header: "Description" },
                  {
                    key: "is_active",
                    header: "Statut",
                    render: (e) =>
                      e.is_active ? (
                        <Badge className="bg-emerald-500 hover:bg-emerald-500">Actif</Badge>
                      ) : (
                        <Badge variant="secondary">Inactif</Badge>
                      ),
                  },
                ]}
                detectActive={(e) => e.is_active}
                defaultForm={{ label: "", description: "" }}
                formFields={[
                  { key: "label", label: "Intitulé", placeholder: "Frais de déplacement" },
                  { key: "description", label: "Description" },
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
              <ManageRows
                title="Catégories marketing"
                rows={country.marketing_categories}
                loading={loading}
                columns={[
                  { key: "name", header: "Nom" },
                  { key: "description", header: "Description" },
                  {
                    key: "is_active",
                    header: "Statut",
                    render: (m) =>
                      m.is_active ? (
                        <Badge className="bg-emerald-500 hover:bg-emerald-500">Active</Badge>
                      ) : (
                        <Badge variant="secondary">Inactive</Badge>
                      ),
                  },
                ]}
                detectActive={(m) => m.is_active}
                defaultForm={{ name: "", description: "" }}
                formFields={[
                  { key: "name", label: "Nom", placeholder: "Marketing digital" },
                  { key: "description", label: "Description" },
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

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <Card className="border-border/60 shadow-sm">
      <CardHeader className="pb-2">
        <CardTitle className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-semibold tracking-tight">{value}</p>
      </CardContent>
    </Card>
  )
}

const STATUS_COLORS: Record<string, string> = {
  planned: "bg-slate-500 hover:bg-slate-500",
  active: "bg-emerald-500 hover:bg-emerald-500",
  on_hold: "bg-amber-500 hover:bg-amber-500",
  completed: "bg-blue-500 hover:bg-blue-500",
}

function StatusBadge({ value }: { value: string }) {
  const labels: Record<string, string> = {
    planned: "Planifié",
    active: "En cours",
    on_hold: "En pause",
    completed: "Terminé",
  }
  return (
    <Badge className={STATUS_COLORS[value] ?? "bg-secondary"}>
      {labels[value] ?? value}
    </Badge>
  )
}