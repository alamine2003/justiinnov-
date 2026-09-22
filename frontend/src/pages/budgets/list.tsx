import { useState } from "react"
import { AlertTriangle, Plus, Wallet } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { BarreEnveloppe, Legende } from "@/components/ui/charts"
import { echelleCommune } from "@/lib/echelle"
import { NativeSelect } from "@/components/ui/native-select"
import { StatCard } from "@/components/ui/stat-card"
import { PageHeader } from "@/components/ui/page-header"
import { TruncatedNotice } from "@/components/ui/truncated-notice"
import { BudgetForm, type BudgetFormValues } from "@/components/budgets/budget-form"
import { EnveloppeDuPays, SousEnveloppes } from "@/components/budgets/country-envelope"
import { Reallocations } from "@/components/budgets/reallocations"
import { useAuth } from "@/context/use-auth"
import { fetchConfiguration } from "@/lib/accounts"
import {
  createBudget,
  fetchBudgetSummary,
  fetchBudgets,
  updateBudget,
} from "@/lib/budgets"
import { fetchCountries, fetchProjects, fetchTeams } from "@/lib/countries"
import { REFERENTIEL_PAGE_SIZE, useReferentiel } from "@/lib/referentiel"
import type { Budget, CountryBudgetRow } from "@/lib/types"
import { useQuery } from "@/lib/use-query"
import { cn, currentYear, formatAmount, yearChoices } from "@/lib/utils"

/**
 * Le plafond est toujours gradué : c'est l'enveloppe elle-même, pas un
 * réglage. Les seuils d'alerte, eux, viennent du profil
 * (`me.alert_thresholds`), que le serveur rend à tous les rôles : un DF lit
 * le même rail qu'un administrateur.
 */
const PLAFOND = 100

export function BudgetsPage() {
  const { t } = useTranslation()
  const { me, can } = useAuth()
  // Attribuer, modifier, arbitrer : trois droits, à la direction par défaut.
  const canCreate = can("budgets.create")
  const canEdit = can("budgets.update")
  const canRequest = can("reallocations.request")
  const canManage = canCreate || canEdit
  // Un seul exercice pour le résumé par pays et la liste des enveloppes :
  // les deux vues parlent des mêmes chiffres. L'année se lit au rendu, pas
  // au chargement du module : l'application reste ouverte au passage de l'an.
  const [year, setYear] = useState(currentYear)
  const years = yearChoices({ before: 2, after: 1 }).reverse()
  // Le pays choisi ouvre son enveloppe et ses sous-enveloppes ; sans pays,
  // tous se comparent en barres.
  const [countryId, setCountryId] = useState<number | "">("")

  const query = useQuery(
    `budgets:${year}`,
    async (signal) => {
      const [budgets, summary] = await Promise.all([
        fetchBudgets({ page_size: REFERENTIEL_PAGE_SIZE, year }, signal),
        fetchBudgetSummary({ year }),
      ])
      return { budgets, summary }
    },
    { fallback: t("budgets.erreur_chargement") },
  )
  const budgets = query.data?.budgets.results ?? []
  const summary = query.data?.summary ?? null

  // Le référentiel du formulaire n'est lu que par qui peut attribuer.
  const countries = useReferentiel(
    "countries",
    () => fetchCountries({ page_size: REFERENTIEL_PAGE_SIZE, is_active: true }),
  )
  const projects = useReferentiel(
    "projects",
    () => fetchProjects({ page_size: REFERENTIEL_PAGE_SIZE, is_active: true }),
    { enabled: canManage },
  )
  const teams = useReferentiel(
    "teams",
    () => fetchTeams({ page_size: REFERENTIEL_PAGE_SIZE, is_active: true }),
    { enabled: canManage },
  )
  // La configuration ne sert plus qu'à proposer la politique de dépassement
  // par défaut dans le formulaire ; elle reste réservée aux administrateurs.
  const configuration = useReferentiel("configuration", fetchConfiguration, {
    enabled: can("configuration.manage"),
  })
  const seuils = me?.alert_thresholds ?? []
  const thresholds = [...new Set([...seuils.filter((s) => s > 0), PLAFOND])].sort((a, b) => a - b)

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<Budget | null>(null)

  const symbolOf = (id: number, fallback: string) =>
    countries.data?.results.find((c) => c.id === id)?.currency_symbol || fallback
  const consolidatedSymbol =
    countries.data?.results.find((c) => c.currency === "XOF")?.currency_symbol || "XOF"

  const rows = summary?.countries ?? []
  // Un compte restreint à un seul pays n'a rien à choisir : son pays s'ouvre
  // de lui-même.
  const selected = countryId === "" && rows.length === 1 ? rows[0] : rows.find((r) => r.country === countryId)
  const sousEnveloppes = selected
    ? budgets.filter((b) => b.country === selected.country && b.scope_kind !== "country")
    : []
  const enveloppePays = selected
    ? budgets.find((b) => b.country === selected.country && b.scope_kind === "country")
    : undefined

  const handleSave = async (values: BudgetFormValues) => {
    if (editing) {
      await updateBudget(editing.id, values)
    } else {
      await createBudget(values)
    }
    setEditing(null)
    query.reload()
  }

  const ouvrirFormulaire = (budget: Budget | null) => {
    setEditing(budget)
    setFormOpen(true)
  }

  const referentielError = countries.error ?? projects.error ?? teams.error

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("budgets.titre")}
        description={t("budgets.description")}
      >
        <div className="flex flex-wrap items-center gap-2">
          {rows.length > 1 && (
            <NativeSelect
              value={countryId}
              onChange={(e) =>
                setCountryId(e.target.value === "" ? "" : Number(e.target.value))
              }
              aria-label={t("commun.pays")}
              className="w-48"
            >
              <option value="">{t("budgets.tous_pays")}</option>
              {rows.map((row) => (
                <option key={row.country} value={row.country}>
                  {row.country_ref ? `${row.country_ref} — ` : ""}
                  {row.country_name}
                </option>
              ))}
            </NativeSelect>
          )}
          <NativeSelect
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            aria-label={t("commun.annee")}
            className="w-28"
          >
            {years.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </NativeSelect>
          {canCreate && (
            <Button onClick={() => ouvrirFormulaire(null)}>
              <Plus className="mr-2 h-4 w-4" aria-hidden />
              {t("budgets.attribuer")}
            </Button>
          )}
        </div>
      </PageHeader>

      {(query.error || referentielError) && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("commun.erreur")}</AlertTitle>
          <AlertDescription>{query.error ?? referentielError}</AlertDescription>
        </Alert>
      )}
      <TruncatedNotice page={query.data?.budgets} noun={t("budgets.noms.enveloppes")} />
      <TruncatedNotice page={countries.data} noun={t("budgets.noms.pays")} />

      {summary && summary.unconverted_currencies.length > 0 && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("budgets.conversion.titre")}</AlertTitle>
          <AlertDescription>
            {t("budgets.conversion.texte", {
              devises: summary.unconverted_currencies.join(", "),
            })}
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard
          icon={Wallet}
          label={t("budgets.indicateurs.disponible_consolide")}
          value={formatAmount(summary?.total_remaining_xof, consolidatedSymbol)}
          hint={t("budgets.indicateurs.taux_en_vigueur")}
        />
        <StatCard
          icon={Wallet}
          label={t("budgets.indicateurs.pays_dotes")}
          value={rows.length}
        />
        <StatCard
          icon={Wallet}
          label={t("budgets.indicateurs.enveloppes")}
          value={query.data?.budgets.count ?? 0}
        />
      </div>

      {rows.length === 0 && !query.loading ? (
        <Card className="border-border/60 shadow-sm">
          <CardContent className="pt-6">
            <div className="rounded-lg border border-dashed border-border/60 p-8 text-center">
              <Wallet className="mx-auto h-5 w-5 text-muted-foreground" aria-hidden />
              <p className="mt-2 text-sm font-medium">{t("budgets.vide.pays_titre")}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {canCreate
                  ? t("budgets.vide.pays_indication_siege")
                  : t("budgets.vide.pays_indication_pays")}
              </p>
            </div>
          </CardContent>
        </Card>
      ) : selected ? (
        <>
          <EnveloppeDuPays
            row={selected}
            budget={enveloppePays}
            thresholds={thresholds}
            symbol={symbolOf(selected.country, selected.currency)}
            onEdit={canEdit ? ouvrirFormulaire : undefined}
          />
          <SousEnveloppes
            budgets={sousEnveloppes}
            row={selected}
            canCreate={canCreate}
            canEdit={canEdit}
            onCreate={() => ouvrirFormulaire(null)}
            onEdit={ouvrirFormulaire}
          />
        </>
      ) : (
        <TousLesPays rows={rows} symbolOf={symbolOf} onChoose={setCountryId} />
      )}

      <Card className="border-border/60 shadow-sm">
        <CardContent className="pt-6">
          <Reallocations
            budgets={budgets}
            canRequest={canRequest}
            onChanged={query.reload}
          />
        </CardContent>
      </Card>

      <BudgetForm
        open={formOpen}
        onOpenChange={(open) => {
          setFormOpen(open)
          if (!open) setEditing(null)
        }}
        onSave={handleSave}
        countries={countries.data?.results ?? []}
        projects={projects.data?.results ?? []}
        teams={teams.data?.results ?? []}
        editing={editing}
        defaultYear={year}
        defaultPolicy={configuration.data?.workflow.default_overrun_policy}
      />
    </div>
  )
}

/**
 * Sans pays choisi : toutes les enveloppes côte à côte, à échelle commune.
 * Chaque barre ouvre le pays — c'est le chemin vers son rail et ses
 * sous-enveloppes.
 */
function TousLesPays({
  rows,
  symbolOf,
  onChoose,
}: {
  rows: CountryBudgetRow[]
  symbolOf: (id: number, fallback: string) => string
  onChoose: (id: number) => void
}) {
  const { t } = useTranslation()
  const echelle = echelleCommune(rows)

  return (
    <Card className="border-border/60 shadow-sm">
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle className="text-sm font-semibold">{t("budgets.onglets.pays")}</CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">
              {t("budgets.choisir_pays")}
            </p>
          </div>
          <Legende
            items={[
              { tone: "bg-marque", label: t("budgets.colonnes.consomme") },
              { tone: "bg-marque-clair", label: t("budgets.colonnes.engage") },
              { tone: "bg-muted", label: t("budgets.colonnes.disponible") },
            ]}
          />
        </div>
      </CardHeader>
      <CardContent>
        <ul className="space-y-4">
          {rows.map((row) => (
            <li key={row.country}>
              <button
                type="button"
                onClick={() => onChoose(row.country)}
                className="w-full rounded-lg p-2 text-left transition-colors hover:bg-accent/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                  <span className="flex items-baseline gap-2">
                    <span className="text-sm font-semibold">{row.country_name}</span>
                    <span className="text-xs text-muted-foreground">
                      {row.country_ref ?? t("commun.aucun")} ·{" "}
                      {symbolOf(row.country, row.currency)}
                    </span>
                  </span>
                  <span className="flex items-baseline gap-2.5 text-xs">
                    <span
                      className={cn(
                        "font-semibold",
                        Number(row.remaining) < 0 ? "text-destructive" : "text-marque-fort",
                      )}
                    >
                      {t("budgets.enveloppe.legende_disponible", {
                        montant: formatAmount(row.remaining),
                      })}
                    </span>
                    <span className="text-muted-foreground">
                      {t("pilotage.barres.attribues", { montant: formatAmount(row.allocated) })}
                    </span>
                  </span>
                </span>
                <span className="mt-1.5 block">
                  <BarreEnveloppe
                    consumed={Number(row.consumed)}
                    engaged={Number(row.engaged)}
                    allocated={Number(row.allocated)}
                    scale={echelle}
                    title={t("budgets.enveloppe.barre_aria", { pays: row.country_name })}
                  />
                </span>
                {Number(row.sub_allocated) > 0 && (
                  <span className="mt-1.5 block text-xs text-muted-foreground">
                    {t("budgets.dont_reparti", { montant: formatAmount(row.sub_allocated) })}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
        <p className="mt-4 border-t border-border/60 pt-3 text-xs text-muted-foreground">
          {t("pilotage.barres.echelle")}
        </p>
      </CardContent>
    </Card>
  )
}
