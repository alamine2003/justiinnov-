import { useState } from "react"
import { AlertTriangle, History, Search } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { NativeSelect } from "@/components/ui/native-select"
import { PAGE_SIZE, Pagination } from "@/components/ui/pagination"
import { EmptyRow, SkeletonRows } from "@/components/ui/table-states"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { DiffList } from "@/components/countries/history"
import { fetchHistory } from "@/lib/countries"
import { HISTORY_ACTIONS, HISTORY_MODELS, historyActionLabel, historyModelLabel } from "@/lib/labels"
import { ACTION_STYLE } from "@/lib/status-styles"
import { useDebouncedValue } from "@/lib/use-debounced"
import { useQuery } from "@/lib/use-query"
import { formatDate } from "@/lib/utils"
import { BarreDePeriode } from "./barre-de-periode"
import { bornes, useFiltresAudit } from "./use-filtres"

/**
 * L'onglet « Référentiel et comptes » : l'historique (`ChangeLog`) — projets,
 * types de dossiers, droits, comptes, connexions, pays, enveloppes. Chaque
 * entrée dit qui, quoi, quand, depuis où, l'avant et l'après, et le motif
 * quand il est exigé (décision 109). La recherche porte aussi sur le motif.
 */
export function JournalDuReferentiel() {
  const { t } = useTranslation()
  const { lire, changer } = useFiltresAudit()
  const page = Math.max(1, Number(lire("page")) || 1)
  const [search, setSearch] = useState(lire("search"))
  const debouncedSearch = useDebouncedValue(search)
  const filtres: Record<string, string> = { ...bornes(lire) }
  for (const cle of ["action", "model_name"]) {
    if (lire(cle)) filtres[cle] = lire(cle)
  }
  if (debouncedSearch) filtres.search = debouncedSearch

  const query = useQuery(
    `historique-audit:${JSON.stringify({ page, filtres })}`,
    (signal) =>
      fetchHistory({ ...filtres, page, page_size: PAGE_SIZE, ordering: "-created_at" }, signal),
    { fallback: t("pays.historique.indisponible") },
  )
  const entries = query.data?.results ?? []
  const count = query.data?.count ?? 0

  return (
    <div className="space-y-4">
      <BarreDePeriode lire={lire} changer={changer} />

      {query.error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("commun.erreur")}</AlertTitle>
          <AlertDescription>{query.error}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-col flex-wrap gap-3 sm:flex-row sm:items-center">
        <div className="relative w-full sm:max-w-xs">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              changer({ page: "" })
            }}
            placeholder={t("audit.referentiel.recherche_placeholder")}
            aria-label={t("audit.referentiel.recherche_aria")}
            className="pl-9"
          />
        </div>
        <NativeSelect
          value={lire("action")}
          onChange={(e) => changer({ action: e.target.value, page: "" })}
          className="sm:max-w-[16rem]"
          aria-label={t("audit.filtre_action_aria")}
        >
          <option value="">{t("audit.toutes_actions")}</option>
          {HISTORY_ACTIONS.map((action) => (
            <option key={action} value={action}>
              {historyActionLabel(t, action)}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          value={lire("model_name")}
          onChange={(e) => changer({ model_name: e.target.value, page: "" })}
          className="sm:max-w-[14rem]"
          aria-label={t("audit.filtres.objet_aria")}
        >
          <option value="">{t("audit.filtres.tous_objets")}</option>
          {HISTORY_MODELS.map((model) => (
            <option key={model} value={model}>
              {historyModelLabel(t, model)}
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
                  <TableHead scope="col">{t("commun.date")}</TableHead>
                  <TableHead scope="col">{t("audit.col_utilisateur")}</TableHead>
                  <TableHead scope="col">{t("audit.col_action")}</TableHead>
                  <TableHead scope="col">{t("audit.col_objet")}</TableHead>
                  <TableHead scope="col">{t("audit.referentiel.col_motif")}</TableHead>
                  <TableHead scope="col">{t("audit.col_detail")}</TableHead>
                  <TableHead scope="col">{t("audit.col_origine")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.loading ? (
                  <SkeletonRows columns={7} />
                ) : entries.length === 0 ? (
                  <EmptyRow
                    colSpan={7}
                    icon={History}
                    title={t("audit.vide_titre")}
                    hint={t("audit.vide_aide")}
                  />
                ) : (
                  entries.map((entry) => (
                    <TableRow key={entry.id}>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatDate(entry.created_at)}
                      </TableCell>
                      <TableCell className="font-medium">
                        {entry.performed_by || t("commun.aucun")}
                      </TableCell>
                      <TableCell>
                        <Badge className={ACTION_STYLE[entry.action] ?? "bg-secondary"}>
                          {entry.action_display}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <p className="text-sm">{entry.label}</p>
                        <p className="text-xs text-muted-foreground">
                          {entry.model_name_display}
                          {entry.object_id !== null && ` #${entry.object_id}`}
                          {entry.country_name && ` · ${entry.country_name}`}
                        </p>
                      </TableCell>
                      <TableCell className="max-w-xs text-sm">
                        {entry.motif || <span className="text-muted-foreground">{t("commun.aucun")}</span>}
                      </TableCell>
                      <TableCell className="max-w-sm text-xs text-muted-foreground">
                        {entry.diff && Object.keys(entry.diff).length > 0 ? (
                          <DiffList diff={entry.diff} />
                        ) : (
                          entry.to_value || entry.from_value || ""
                        )}
                      </TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {entry.ip_address ?? t("commun.aucun")}
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
            onChange={(suivante) => changer({ page: suivante > 1 ? String(suivante) : "" })}
            noun={[t("audit.noun_singulier"), t("audit.noun_pluriel")]}
          />
        </CardContent>
      </Card>
    </div>
  )
}
