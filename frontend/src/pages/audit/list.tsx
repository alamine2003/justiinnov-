import { useState } from "react"
import { AlertTriangle, ScrollText, Search } from "lucide-react"
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
import { fetchAudit } from "@/lib/expenses"
import { ACTION_STYLE } from "@/lib/status-styles"
import { AUDIT_ACTION_LABELS, type AuditEntry } from "@/lib/types"
import { useDebouncedValue } from "@/lib/use-debounced"
import { useQuery } from "@/lib/use-query"
import { formatDate } from "@/lib/utils"

/** Résume le détail JSON d'une entrée en une phrase lisible. */
function summarize(entry: AuditEntry): string {
  const detail = entry.detail ?? {}
  const parts: string[] = []
  if (typeof detail.from_status === "string" && typeof detail.to_status === "string") {
    parts.push(`${detail.from_status} → ${detail.to_status}`)
  }
  if (typeof detail.note === "string" && detail.note) parts.push(`« ${detail.note} »`)
  if (typeof detail.reason === "string" && detail.reason) parts.push(`« ${detail.reason} »`)
  const before = detail.before as Record<string, string> | undefined
  const after = detail.after as Record<string, string> | undefined
  if (before && after && before.amount !== after.amount) {
    parts.push(`montant ${before.amount} → ${after.amount}`)
  }
  if (typeof detail.sha256 === "string") {
    parts.push(`empreinte ${detail.sha256.slice(0, 12)}…`)
  }
  return parts.join(" · ")
}

export function AuditPage() {
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
    { fallback: "Impossible de charger le journal" },
  )
  const entries = query.data?.results ?? []
  const count = query.data?.count ?? 0

  return (
    <div className="space-y-6">
      <PageHeader
        title="Journal d'audit"
        description="Qui a fait quoi, quand et depuis quelle adresse. Les entrées ne sont ni modifiables ni supprimables."
      />

      {query.error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Erreur</AlertTitle>
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
            placeholder="Utilisateur ou libellé…"
            aria-label="Rechercher dans le journal"
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
          aria-label="Filtrer par action"
        >
          <option value="">Toutes les actions</option>
          {Object.entries(AUDIT_ACTION_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
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
                  <TableHead scope="col">Date</TableHead>
                  <TableHead scope="col">Utilisateur</TableHead>
                  <TableHead scope="col">Action</TableHead>
                  <TableHead scope="col">Objet</TableHead>
                  <TableHead scope="col">Détail</TableHead>
                  <TableHead scope="col">Origine</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.loading ? (
                  <SkeletonRows columns={6} />
                ) : entries.length === 0 ? (
                  <EmptyRow
                    colSpan={6}
                    icon={ScrollText}
                    title="Aucune entrée"
                    hint="Le journal se remplit à mesure des actions."
                  />
                ) : (
                  entries.map((entry) => (
                    <TableRow key={entry.id}>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatDate(entry.created_at)}
                      </TableCell>
                      <TableCell className="font-medium">{entry.user || "—"}</TableCell>
                      <TableCell>
                        <Badge className={ACTION_STYLE[entry.action] ?? "bg-secondary"}>
                          {entry.action_display}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <p className="text-sm">{entry.label}</p>
                        <p className="text-xs text-muted-foreground">
                          {entry.object_type} #{entry.object_id}
                          {entry.country_name && ` · ${entry.country_name}`}
                        </p>
                      </TableCell>
                      <TableCell className="max-w-sm text-xs text-muted-foreground">
                        {summarize(entry)}
                      </TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {entry.ip_address ?? "—"}
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
            noun={["entrée", "entrées"]}
          />
        </CardContent>
      </Card>
    </div>
  )
}
