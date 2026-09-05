import { useState } from "react"
import { AlertTriangle, ScrollText, Search } from "lucide-react"
import { useTranslation } from "react-i18next"
import type { TFunction } from "i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { NativeSelect } from "@/components/ui/native-select"
import { PAGE_SIZE, Pagination } from "@/components/ui/pagination"
import { PageHeader } from "@/components/ui/page-header"
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
import { fetchAudit } from "@/lib/expenses"
import { AUDIT_ACTIONS, auditActionLabel } from "@/lib/labels"
import { ACTION_STYLE } from "@/lib/status-styles"
import { type AuditEntry } from "@/lib/types"
import { useDebouncedValue } from "@/lib/use-debounced"
import { useQuery } from "@/lib/use-query"
import { formatDate } from "@/lib/utils"

/** Résume le détail JSON d'une entrée en une phrase lisible. */
function summarize(t: TFunction, entry: AuditEntry): string {
  const detail = entry.detail ?? {}
  const parts: string[] = []
  if (typeof detail.from_status === "string" && typeof detail.to_status === "string") {
    parts.push(`${detail.from_status} → ${detail.to_status}`)
  }
  if (typeof detail.note === "string" && detail.note) {
    parts.push(t("audit.detail_citation", { texte: detail.note }))
  }
  if (typeof detail.reason === "string" && detail.reason) {
    parts.push(t("audit.detail_citation", { texte: detail.reason }))
  }
  const before = detail.before as Record<string, string> | undefined
  const after = detail.after as Record<string, string> | undefined
  if (before && after && before.amount !== after.amount) {
    parts.push(t("audit.detail_montant", { avant: before.amount, apres: after.amount }))
  }
  if (typeof detail.sha256 === "string") {
    parts.push(t("audit.detail_empreinte", { empreinte: detail.sha256.slice(0, 12) }))
  }
  return parts.join(" · ")
}

/** Ancienne et nouvelle valeur par champ, quand le serveur les a jointes au détail. */
function readDiff(entry: AuditEntry): Record<string, [unknown, unknown]> | null {
  const diff = entry.detail?.diff
  if (!diff || typeof diff !== "object" || Array.isArray(diff)) return null
  const entries = Object.entries(diff as Record<string, unknown>).filter(
    (pair): pair is [string, [unknown, unknown]] => Array.isArray(pair[1]) && pair[1].length === 2,
  )
  return entries.length > 0 ? Object.fromEntries(entries) : null
}

export function AuditPage() {
  const { t } = useTranslation()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState("")
  const debouncedSearch = useDebouncedValue(search)
  const [actionFilter, setActionFilter] = useState("")

  const query = useQuery(
    JSON.stringify({ page, debouncedSearch, actionFilter }),
    (signal) => {
      const params: Record<string, unknown> = {
        page,
        page_size: PAGE_SIZE,
        ordering: "-created_at",
      }
      if (debouncedSearch) params.search = debouncedSearch
      if (actionFilter) params.action = actionFilter
      return fetchAudit(params, signal)
    },
    { fallback: t("audit.chargement_impossible") },
  )
  const entries = query.data?.results ?? []
  const count = query.data?.count ?? 0

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("audit.titre")}
        description={t("audit.description")}
      />

      {query.error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("commun.erreur")}</AlertTitle>
          <AlertDescription>{query.error}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative w-full sm:max-w-xs">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(1)
            }}
            placeholder={t("audit.recherche_placeholder")}
            aria-label={t("audit.recherche_aria")}
            className="pl-9"
          />
        </div>
        <NativeSelect
          value={actionFilter}
          onChange={(e) => {
            setActionFilter(e.target.value)
            setPage(1)
          }}
          className="sm:max-w-[16rem]"
          aria-label={t("audit.filtre_action_aria")}
        >
          <option value="">{t("audit.toutes_actions")}</option>
          {AUDIT_ACTIONS.map((action) => (
            <option key={action} value={action}>
              {auditActionLabel(t, action)}
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
                  <TableHead scope="col">{t("audit.col_detail")}</TableHead>
                  <TableHead scope="col">{t("audit.col_origine")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.loading ? (
                  <SkeletonRows columns={6} />
                ) : entries.length === 0 ? (
                  <EmptyRow
                    colSpan={6}
                    icon={ScrollText}
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
                        {entry.user || t("commun.aucun")}
                      </TableCell>
                      <TableCell>
                        <Badge className={ACTION_STYLE[entry.action] ?? "bg-secondary"}>
                          {entry.action_display}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <p className="text-sm">{entry.label}</p>
                        <p className="text-xs text-muted-foreground">
                          {entry.object_type}
                          {entry.object_id !== null && ` #${entry.object_id}`}
                          {entry.country_name && ` · ${entry.country_name}`}
                        </p>
                      </TableCell>
                      <TableCell className="max-w-sm text-xs text-muted-foreground">
                        {summarize(t, entry)}
                        {readDiff(entry) && <DiffList diff={readDiff(entry)!} />}
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
            onChange={setPage}
            noun={[t("audit.noun_singulier"), t("audit.noun_pluriel")]}
          />
        </CardContent>
      </Card>
    </div>
  )
}
