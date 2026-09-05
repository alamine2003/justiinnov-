import { useState, type FormEvent } from "react"
import { Link, useSearchParams } from "react-router-dom"
import { AlertTriangle, FolderOpen, Loader2, Plus, Search } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { FormError } from "@/components/ui/form-error"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { PAGE_SIZE, Pagination } from "@/components/ui/pagination"
import { PageHeader } from "@/components/ui/page-header"
import { EmptyRow, SkeletonRows } from "@/components/ui/table-states"
import { TruncatedNotice } from "@/components/ui/truncated-notice"
import { StatusBadge } from "@/components/expenses/status-badge"
import { ExportMenu } from "@/components/reporting/export-menu"
import { useAuth } from "@/context/use-auth"
import { createDossier, fetchDossiers } from "@/lib/expenses"
import { fetchCountries, fetchCountry } from "@/lib/countries"
import { WORKFLOW_STATUSES, workflowLabel } from "@/lib/labels"
import { REFERENTIEL_PAGE_SIZE, useReferentiel } from "@/lib/referentiel"
import { scopedTeams, teamRequired } from "@/lib/teams"
import type { CountrySummary, WorkflowStatus } from "@/lib/types"
import { useDebouncedValue } from "@/lib/use-debounced"
import { useQuery } from "@/lib/use-query"
import { cn, formatAmount, formatDay, todayIso } from "@/lib/utils"

export function DossiersPage() {
  const { t } = useTranslation()
  const { can } = useAuth()
  const canCreate = can("expenses.create")
  const [params, setParams] = useSearchParams()

  // Le statut vit dans l'URL : une tuile du tableau de bord ou un favori
  // doivent rouvrir la même vue.
  const statusParam = params.get("status") ?? ""
  const statusFilter = (WORKFLOW_STATUSES as string[]).includes(statusParam)
    ? (statusParam as WorkflowStatus)
    : ""

  const [page, setPage] = useState(1)
  const [search, setSearch] = useState("")
  const debouncedSearch = useDebouncedValue(search)
  const [formOpen, setFormOpen] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)

  const query = useQuery(
    JSON.stringify({ page, search: debouncedSearch, statusFilter }),
    (signal) => {
      const requestParams: Record<string, unknown> = { page, page_size: PAGE_SIZE }
      if (debouncedSearch) requestParams.search = debouncedSearch
      if (statusFilter) requestParams.status = statusFilter
      return fetchDossiers(requestParams, signal)
    },
    { fallback: t("dossiers.liste.chargement_impossible") },
  )
  const countries = useReferentiel("countries", () =>
    fetchCountries({ page_size: REFERENTIEL_PAGE_SIZE, is_active: true }),
  )

  const dossiers = query.data?.results ?? []
  const count = query.data?.count ?? 0

  // Un changement de filtre ramène à la première page : rester en page 4
  // d'un résultat qui n'en compte plus qu'une afficherait un tableau vide.
  const changeStatus = (value: string) => {
    setPage(1)
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (value) next.set("status", value)
        else next.delete("status")
        return next
      },
      { replace: true },
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("dossiers.liste.titre")}
        description={t("dossiers.liste.description")}
      >
        <ExportMenu onError={setExportError} />
        {canCreate && (
          <Button onClick={() => setFormOpen(true)}>
            <Plus className="mr-2 h-4 w-4" aria-hidden />
            {t("dossiers.liste.nouveau")}
          </Button>
        )}
      </PageHeader>

      {(query.error || exportError) && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("commun.erreur")}</AlertTitle>
          <AlertDescription>{exportError ?? query.error}</AlertDescription>
        </Alert>
      )}
      <TruncatedNotice page={countries.data} noun={t("dossiers.noms_pays")} />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative w-full sm:max-w-xs">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(1)
            }}
            placeholder={t("dossiers.liste.recherche_placeholder")}
            aria-label={t("dossiers.liste.recherche_aria")}
            className="pl-9"
          />
        </div>
        <NativeSelect
          value={statusFilter}
          onChange={(e) => changeStatus(e.target.value)}
          className="sm:max-w-[12rem]"
          aria-label={t("dossiers.liste.filtrer_statut")}
        >
          <option value="">{t("dossiers.liste.tous_statuts")}</option>
          {WORKFLOW_STATUSES.map((value) => (
            <option key={value} value={value}>
              {workflowLabel(t, value)}
            </option>
          ))}
        </NativeSelect>
      </div>

      <Card className="border-border/60 shadow-sm">
        <CardContent className="pt-6">
          <div className="overflow-x-auto rounded-lg border border-border/60">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">{t("champs.number")}</TableHead>
                  <TableHead scope="col">{t("commun.pays")}</TableHead>
                  <TableHead scope="col">{t("commun.date")}</TableHead>
                  <TableHead scope="col" className="text-center">{t("dossiers.liste.colonnes.lignes")}</TableHead>
                  <TableHead scope="col" className="text-center">{t("dossiers.liste.colonnes.preuves")}</TableHead>
                  <TableHead scope="col" className="text-right">{t("dossiers.liste.colonnes.depenses")}</TableHead>
                  <TableHead scope="col" className="text-right">{t("dossiers.liste.colonnes.ecart")}</TableHead>
                  <TableHead scope="col">{t("commun.statut")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.loading ? (
                  <SkeletonRows columns={8} />
                ) : dossiers.length === 0 ? (
                  <EmptyRow
                    colSpan={8}
                    icon={FolderOpen}
                    title={t("dossiers.liste.vide.titre")}
                    hint={
                      canCreate
                        ? t("dossiers.liste.vide.aide_creer")
                        : t("dossiers.liste.vide.aide_filtres")
                    }
                  />
                ) : (
                  dossiers.map((dossier) => (
                    <TableRow key={dossier.id}>
                      <TableCell>
                        {/* Le lien porte la navigation : accessible au
                            clavier, ouvrable dans un nouvel onglet. */}
                        <Link
                          to={`/dossiers/${dossier.id}`}
                          className="font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        >
                          {dossier.number}
                        </Link>
                        <p className="text-xs text-muted-foreground">{dossier.label}</p>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {dossier.country_ref ?? dossier.country_name}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatDay(dossier.date)}
                      </TableCell>
                      <TableCell className="text-center">{dossier.expense_count}</TableCell>
                      <TableCell className="text-center">{dossier.proof_count}</TableCell>
                      <TableCell className="text-right">
                        {formatAmount(dossier.totals.amount, dossier.currency)}
                      </TableCell>
                      <TableCell
                        className={cn(
                          "text-right",
                          Number(dossier.totals.gap) > 0 && "font-medium text-destructive",
                        )}
                      >
                        {formatAmount(dossier.totals.gap)}
                      </TableCell>
                      <TableCell>
                        <StatusBadge status={dossier.status} label={dossier.status_display} />
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>

          <Pagination
            page={page}
            count={count}
            onChange={setPage}
            noun={[t("dossiers.nom_one"), t("dossiers.nom_other")]}
          />
        </CardContent>
      </Card>

      {formOpen && (
        <DossierForm
          onOpenChange={setFormOpen}
          countries={countries.data?.results ?? []}
          onSaved={async () => {
            query.reload()
          }}
        />
      )}
    </div>
  )
}

function DossierForm({
  onOpenChange,
  countries,
  onSaved,
}: {
  onOpenChange: (open: boolean) => void
  countries: CountrySummary[]
  onSaved: () => Promise<void>
}) {
  const { t } = useTranslation()
  const { me } = useAuth()
  const [number, setNumber] = useState("")
  const [label, setLabel] = useState("")
  const [country, setCountry] = useState<number | "">(countries[0]?.id ?? "")
  const [team, setTeam] = useState<number | "">("")
  const [owner, setOwner] = useState<number | "">("")
  const [date, setDate] = useState(todayIso())
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  // Équipes et managers du pays choisi, depuis sa fiche : la seule liste qui
  // sache quel manager est rattaché à quel pays.
  const detail = useReferentiel(
    `country:${country}`,
    () => fetchCountry(Number(country)),
    { enabled: country !== "" },
  )
  // Un manager rattaché à des équipes n'ouvre un dossier que pour elles.
  const teams = scopedTeams(
    (detail.data?.teams ?? []).filter((equipe) => equipe.is_active),
    me,
  )
  const managers = (detail.data?.managers ?? []).filter((m) => m.is_active)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (country === "") {
      setError(t("dossiers.formulaire.choisir_pays"))
      return
    }
    if (teamRequired(me) && team === "") {
      setError(t("dossiers.formulaire.equipe_requise"))
      return
    }
    setSaving(true)
    setError(null)
    try {
      await createDossier({
        number,
        label,
        country,
        team: team === "" ? null : team,
        owner: owner === "" ? null : owner,
        date,
      })
      await onSaved()
      onOpenChange(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : t("dossiers.formulaire.creation_impossible"))
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("dossiers.liste.nouveau")}</DialogTitle>
          <DialogDescription>{t("dossiers.formulaire.description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-4 py-2" noValidate>
          <FormError>{error}</FormError>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="dos-number">{t("champs.number")}</Label>
              <Input
                id="dos-number"
                value={number}
                onChange={(e) => setNumber(e.target.value)}
                placeholder={t("dossiers.formulaire.numero_placeholder")}
                required
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="dos-date">{t("commun.date")}</Label>
              <Input
                id="dos-date"
                type="date"
                value={date}
                onChange={(e) => setDate(e.target.value)}
                required
              />
            </div>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="dos-label">{t("champs.label")}</Label>
            <Input
              id="dos-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder={t("dossiers.formulaire.libelle_placeholder")}
              required
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="dos-country">{t("commun.pays")}</Label>
            <NativeSelect
              id="dos-country"
              value={country}
              onChange={(e) => {
                setCountry(e.target.value === "" ? "" : Number(e.target.value))
                setTeam("")
                setOwner("")
              }}
              required
            >
              {countries.length === 0 && (
                <option value="">{t("dossiers.formulaire.aucun_pays")}</option>
              )}
              {countries.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.country_ref ? `${c.country_ref} — ` : ""}
                  {c.name}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="grid gap-2">
              <Label htmlFor="dos-team">{t("champs.team")}</Label>
              <NativeSelect
                id="dos-team"
                value={team}
                onChange={(e) =>
                  setTeam(e.target.value === "" ? "" : Number(e.target.value))
                }
                disabled={detail.loading}
                required={teamRequired(me)}
              >
                <option value="">{t("commun.aucun")}</option>
                {teams.map((equipe) => (
                  <option key={equipe.id} value={equipe.id}>
                    {equipe.name}
                  </option>
                ))}
              </NativeSelect>
            </div>
            <div className="grid gap-2">
              <Label htmlFor="dos-owner">{t("dossiers.formulaire.manager_responsable")}</Label>
              <NativeSelect
                id="dos-owner"
                value={owner}
                onChange={(e) =>
                  setOwner(e.target.value === "" ? "" : Number(e.target.value))
                }
                disabled={detail.loading}
              >
                <option value="">{t("commun.aucun")}</option>
                {managers.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </NativeSelect>
            </div>
          </div>
          {detail.error && <FormError>{detail.error}</FormError>}
          <DialogFooter>
            <div>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t("commun.annuler")}
              </Button>
              <Button type="submit" disabled={saving} className="ml-2">
                {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {t("commun.creer")}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
