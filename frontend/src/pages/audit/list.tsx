import { useCallback, useEffect, useState } from "react"
import { AlertTriangle, ScrollText, Search } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { NativeSelect } from "@/components/ui/native-select"
import { PAGE_SIZE, Pagination } from "@/components/ui/pagination"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { fetchAudit } from "@/lib/expenses"
import type { AuditEntry } from "@/lib/types"
import { formatDate } from "@/lib/utils"

const ACTION_STYLE: Record<string, string> = {
  justified: "bg-emerald-500 hover:bg-emerald-500",
  unjustified: "bg-destructive hover:bg-destructive",
  approved: "bg-emerald-500 hover:bg-emerald-500",
  rejected: "bg-destructive hover:bg-destructive",
  submitted: "bg-blue-500 hover:bg-blue-500",
  reviewed: "bg-amber-500 hover:bg-amber-500",
  deleted: "bg-zinc-600 hover:bg-zinc-600",
  downloaded: "bg-zinc-500 hover:bg-zinc-500",
}

/**
 * Valeurs proposées au filtre. Les libellés affichés viennent du serveur
 * (`action_display`) : les recopier ici les ferait diverger.
 */
const FILTERABLE_ACTIONS = [
  ["created", "Création"],
  ["updated", "Modification"],
  ["deleted", "Suppression d'un brouillon"],
  ["submitted", "Soumission"],
  ["reviewed", "Mise en contrôle"],
  ["justified", "Justification"],
  ["unjustified", "Constat de non-justification"],
  ["closed", "Clôture"],
  ["proof_uploaded", "Dépôt de justificatif"],
  ["proof_replaced", "Remplacement de justificatif"],
  ["approved", "Validation d'un justificatif"],
  ["rejected", "Rejet d'un justificatif"],
  ["downloaded", "Téléchargement"],
] as const

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
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [count, setCount] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [actionFilter, setActionFilter] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: Record<string, unknown> = {
        page,
        page_size: PAGE_SIZE,
        ordering: "-created_at",
      }
      if (search) params.search = search
      if (actionFilter) params.action = actionFilter
      const result = await fetchAudit(params)
      setEntries(result.results)
      setCount(result.count)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Impossible de charger le journal")
    } finally {
      setLoading(false)
    }
  }, [page, search, actionFilter])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    setPage(1)
  }, [search, actionFilter])

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Journal d'audit</h1>
        <p className="text-sm text-muted-foreground">
          Qui a fait quoi, quand et depuis quelle adresse. Les entrées ne sont ni
          modifiables ni supprimables.
        </p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>Erreur</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative w-full sm:max-w-xs">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Utilisateur ou libellé…"
            className="pl-9"
          />
        </div>
        <NativeSelect
          value={actionFilter}
          onChange={(e) => setActionFilter(e.target.value)}
          className="sm:max-w-[16rem]"
          aria-label="Filtrer par action"
        >
          <option value="">Toutes les actions</option>
          {FILTERABLE_ACTIONS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </NativeSelect>
      </div>

      <Card className="border-border/60 shadow-sm">
        <CardContent className="pt-6">
          <div className="overflow-hidden rounded-lg border border-border/60">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Utilisateur</TableHead>
                  <TableHead>Action</TableHead>
                  <TableHead>Objet</TableHead>
                  <TableHead>Détail</TableHead>
                  <TableHead>Origine</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={6} className="h-16">
                      <div className="h-4 animate-pulse rounded bg-muted" />
                    </TableCell>
                  </TableRow>
                ) : entries.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="h-24 text-center text-muted-foreground">
                      <ScrollText className="mx-auto mb-2 h-6 w-6 opacity-60" />
                      Aucune entrée.
                    </TableCell>
                  </TableRow>
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
