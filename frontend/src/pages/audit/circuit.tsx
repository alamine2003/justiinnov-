import { useState } from "react"
import { AlertTriangle, ScrollText, Search, X } from "lucide-react"
import { useTranslation } from "react-i18next"
import type { TFunction } from "i18next"
import type { WorkflowStatus } from "@/lib/types"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
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
import { fetchAudit } from "@/lib/expenses"
import { AUDIT_ACTIONS, auditActionLabel } from "@/lib/labels"
import { ACTION_STYLE } from "@/lib/status-styles"
import { type AuditEntry } from "@/lib/types"
import { useDebouncedValue } from "@/lib/use-debounced"
import { useQuery } from "@/lib/use-query"
import { formatAmount, formatDate } from "@/lib/utils"
import { workflowLabel } from "@/lib/labels"
import { BarreDePeriode } from "./barre-de-periode"
import { bornes, useFiltresAudit } from "./use-filtres"

/** Résume le détail JSON d'une entrée en une phrase lisible. */
function summarize(t: TFunction, entry: AuditEntry): string {
  const detail = entry.detail ?? {}
  const parts: string[] = []
  if (typeof detail.from_status === "string" && typeof detail.to_status === "string") {
    // Les codes du circuit sortaient bruts — « draft → submitted », en
    // français comme en anglais. Ils passent par la table des libellés,
    // comme partout ailleurs.
    parts.push(
      `${workflowLabel(t, detail.from_status as WorkflowStatus)} → ${workflowLabel(t, detail.to_status as WorkflowStatus)}`,
    )
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
    // « 1500.00 → 1200.00 » : un montant s'affiche formaté, ici comme ailleurs.
    parts.push(
      t("audit.detail_montant", {
        avant: formatAmount(before.amount),
        apres: formatAmount(after.amount),
      }),
    )
  }
  if (typeof detail.sha256 === "string") {
    parts.push(t("audit.detail_empreinte", { empreinte: detail.sha256.slice(0, 12) }))
  }
  return parts.join(" · ")
}

/** Ancienne et nouvelle valeur par champ, quand le serveur les a jointes au détail. */
function readDiff(entry: AuditEntry): Record<string, [unknown, unknown]> | null {
  const diff = entry.detail?.diff
  const avant = entry.detail?.before
  const apres = entry.detail?.after
  // Un renommage (décision 104) porte son avant et son après, sans `diff`.
  if (!diff && entry.action === "renamed" && avant && apres) {
    const a = avant as Record<string, unknown>
    const b = apres as Record<string, unknown>
    return Object.fromEntries(Object.keys(b).map((champ) => [champ, [a[champ], b[champ]]]))
  }
  if (!diff || typeof diff !== "object" || Array.isArray(diff)) return null
  const entries = Object.entries(diff as Record<string, unknown>).filter(
    (pair): pair is [string, [unknown, unknown]] => Array.isArray(pair[1]) && pair[1].length === 2,
  )
  return entries.length > 0 ? Object.fromEntries(entries) : null
}

/** Objets du journal du circuit, pour le filtre « Objet ». */
const OBJETS = [
  "Dossier", "Expense", "Proof", "Rectification", "BudgetReallocation", "Export", "ExpenseImport",
] as const

/**
 * L'onglet « Circuit » : le journal d'audit, filtrable par période, pays,
 * action, objet, utilisateur et projet. Les filtres vivent dans l'URL : la
 * vue d'ensemble et l'historique d'un projet y mènent déjà filtrés.
 */
export function JournalDuCircuit() {
  const { t } = useTranslation()
  const { lire, changer } = useFiltresAudit()
  const page = Math.max(1, Number(lire("page")) || 1)
  const [search, setSearch] = useState(lire("search"))
  const debouncedSearch = useDebouncedValue(search)
  const filtres: Record<string, string> = { ...bornes(lire) }
  for (const cle of ["action", "object_type", "user", "projet"]) {
    if (lire(cle)) filtres[cle] = lire(cle)
  }
  if (debouncedSearch) filtres.search = debouncedSearch

  const query = useQuery(
    JSON.stringify({ page, filtres }),
    (signal) =>
      fetchAudit({ ...filtres, page, page_size: PAGE_SIZE, ordering: "-created_at" }, signal),
    { fallback: t("audit.chargement_impossible") },
  )
  const entries = query.data?.results ?? []
  const count = query.data?.count ?? 0

  return (
    <div className="remplit space-y-4 court:space-y-3">
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
            placeholder={t("audit.recherche_placeholder")}
            aria-label={t("audit.recherche_aria")}
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
          {AUDIT_ACTIONS.map((action) => (
            <option key={action} value={action}>
              {auditActionLabel(t, action)}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          value={lire("object_type")}
          onChange={(e) => changer({ object_type: e.target.value, page: "" })}
          className="sm:max-w-[12rem]"
          aria-label={t("audit.filtres.objet_aria")}
        >
          <option value="">{t("audit.filtres.tous_objets")}</option>
          {OBJETS.map((objet) => (
            <option key={objet} value={objet}>
              {t(`audit.filtres.objets.${objet}`)}
            </option>
          ))}
        </NativeSelect>
        {(lire("user") || lire("projet")) && (
          <div className="flex flex-wrap gap-2">
            {lire("user") && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => changer({ user: "", page: "" })}
                aria-label={t("audit.filtres.retirer", { filtre: t("audit.filtres.utilisateur", { nom: lire("user") }) })}
              >
                {t("audit.filtres.utilisateur", { nom: lire("user") })}
                <X className="ml-1 h-3.5 w-3.5" aria-hidden />
              </Button>
            )}
            {lire("projet") && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => changer({ projet: "", page: "" })}
                aria-label={t("audit.filtres.retirer", { filtre: t("audit.filtres.projet", { id: lire("projet") }) })}
              >
                {t("audit.filtres.projet", { id: lire("projet") })}
                <X className="ml-1 h-3.5 w-3.5" aria-hidden />
              </Button>
            )}
          </div>
        )}
      </div>

      <Card className="remplit border-border/60 shadow-sm">
        <CardContent className="remplit">
          <div className="defile overflow-x-auto rounded-lg border border-border/60">
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
                          {/* Le serveur nomme l'objet par sa classe (« Expense ») :
                              traduit, comme dans `Evenement`. */}
                          {t(`audit.objet.${entry.object_type}` as "audit.objet.Dossier", {
                            defaultValue: entry.object_type,
                          })}
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
            onChange={(suivante) => changer({ page: suivante > 1 ? String(suivante) : "" })}
            noun={[t("audit.noun_singulier"), t("audit.noun_pluriel")]}
          />
        </CardContent>
      </Card>
    </div>
  )
}
