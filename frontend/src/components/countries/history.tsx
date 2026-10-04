import type { TFunction } from "i18next"
import { History } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { FormError } from "@/components/ui/form-error"
import { TruncatedNotice } from "@/components/ui/truncated-notice"
import { fetchHistory } from "@/lib/countries"
import { ACTION_STYLE } from "@/lib/status-styles"
import type { ChangeLogEntry } from "@/lib/types"
import { useQuery } from "@/lib/use-query"
import { formatAmount, formatDate } from "@/lib/utils"

/** Ce qui a changé, selon l'action, à partir des valeurs du serveur. */
function describe(t: TFunction, entry: ChangeLogEntry): string {
  const parts = [entry.model_name_display]
  if (entry.action === "reassigned") {
    if (entry.from_value) parts.push(t("pays.historique.de", { valeur: entry.from_value }))
    if (entry.to_value) parts.push(t("pays.historique.vers", { valeur: entry.to_value }))
  } else if (entry.action === "updated") {
    // Le détail champ par champ (`diff`) est rendu à part ; ici, seulement
    // ce qu'un serveur sans `diff` fournit.
    if (!hasDiff(entry) && entry.changed_fields.length > 0) {
      parts.push(t("pays.historique.champs", { liste: entry.changed_fields.join(", ") }))
    }
    if (!hasDiff(entry) && (entry.from_value || entry.to_value)) {
      const avant = entry.from_value || t("commun.aucun")
      const apres = entry.to_value || t("commun.aucun")
      parts.push(`${avant} → ${apres}`)
    }
  } else if (entry.to_value) {
    parts.push(entry.to_value)
  }
  return parts.join(" · ")
}

function hasDiff(entry: ChangeLogEntry): boolean {
  return Boolean(entry.diff && Object.keys(entry.diff).length > 0)
}

/**
 * Champs monétaires du journal : ils se lisent formatés, comme partout.
 * Pas `budget` : dans le journal du circuit, c'est l'enveloppe imputée — un
 * identifiant —, et un identifiant ne se formate pas en montant.
 */
const MONTANTS = new Set(["amount", "justified_amount", "original_amount"])

/** Le libellé d'un champ, traduit quand l'interface le connaît. */
function libelleDuChamp(t: TFunction, champ: string): string {
  return t(`champs.${champ}` as "champs.name", { defaultValue: champ })
}

/**
 * Une valeur du journal, lisible : « — » pour le vide, un statut par son
 * libellé (circuit, pièce ou projet), un montant formaté, JSON pour un
 * objet. Mettre en forme n'est pas calculer : la valeur est celle du
 * serveur.
 */
function formatDiffValue(t: TFunction, champ: string, value: unknown): string {
  if (value === null || value === undefined || value === "") return t("commun.aucun")
  if (typeof value === "boolean") return value ? t("commun.oui") : t("commun.non")
  if (typeof value === "object") return JSON.stringify(value)
  if (champ === "status" && typeof value === "string") {
    return t(`libelles.workflow.${value}` as "libelles.workflow.draft", {
      defaultValue: t(`libelles.piece_statut.${value}` as "libelles.piece_statut.received", {
        defaultValue: t(`libelles.projet_statut.${value}` as "libelles.projet_statut.active", {
          defaultValue: value,
        }),
      }),
    })
  }
  if (MONTANTS.has(champ) && (typeof value === "string" || typeof value === "number")) {
    return formatAmount(String(value))
  }
  return String(value)
}

/**
 * Ancienne et nouvelle valeur, champ par champ — seulement ce qui a changé,
 * sous le nom du champ plutôt que son code.
 */
export function DiffList({ diff }: { diff: Record<string, [unknown, unknown]> }) {
  const { t } = useTranslation()
  const lignes = Object.entries(diff)
    .map(([champ, [avant, apres]]) => ({
      champ,
      avant: formatDiffValue(t, champ, avant),
      apres: formatDiffValue(t, champ, apres),
    }))
    .filter((ligne) => ligne.avant !== ligne.apres)
  if (lignes.length === 0) return null
  return (
    <dl className="mt-1 grid gap-0.5 text-xs text-muted-foreground">
      {lignes.map(({ champ, avant, apres }) => (
        <div key={champ} className="flex flex-wrap gap-x-1">
          <dt className="font-medium">{libelleDuChamp(t, champ)}{t("commun.separateur_libelle")}</dt>
          <dd>
            <span className="line-through">{avant}</span>
            {" → "}
            <span className="text-foreground">{apres}</span>
          </dd>
        </div>
      ))}
    </dl>
  )
}

export function CaretHistory({ countryId }: { countryId: number }) {
  const { t } = useTranslation()
  const query = useQuery(
    `history:${countryId}`,
    (signal) => fetchHistory({ country: countryId, page_size: 100 }, signal),
    { fallback: t("pays.historique.indisponible") },
  )
  const entries = query.data?.results ?? []

  if (query.loading) {
    return (
      <div className="space-y-3" aria-busy="true">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-14 animate-pulse rounded-lg bg-muted" />
        ))}
      </div>
    )
  }

  if (query.error) {
    return <FormError>{query.error}</FormError>
  }

  if (entries.length === 0) {
    return (
      <Card className="flex flex-col items-center justify-center gap-2 border-dashed border-border/60 p-10 text-center">
        <History className="h-8 w-8 text-muted-foreground/60" aria-hidden />
        <p className="text-sm font-medium">{t("pays.historique.vide_titre")}</p>
        <p className="text-xs text-muted-foreground">{t("pays.historique.vide_texte")}</p>
      </Card>
    )
  }

  return (
    <div className="space-y-2">
      <TruncatedNotice page={query.data} noun={t("pays.historique.nom_pluriel")} />
      {entries.map((entry) => (
        <div
          key={entry.id}
          className="flex items-start justify-between gap-4 rounded-lg border border-border/60 p-4 shadow-sm transition-colors hover:bg-accent/30"
        >
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Badge className={ACTION_STYLE[entry.action] ?? "bg-secondary"}>
                {entry.action_display}
              </Badge>
              <span className="font-medium">{entry.label}</span>
            </div>
            <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
              {describe(t, entry)}
            </p>
            {hasDiff(entry) && <DiffList diff={entry.diff!} />}
          </div>
          <div className="shrink-0 text-right text-xs text-muted-foreground">
            <p>{formatDate(entry.created_at)}</p>
            {entry.performed_by && (
              <p className="font-medium">{t("pays.historique.par", { nom: entry.performed_by })}</p>
            )}
            {entry.ip_address && <p className="font-mono">{entry.ip_address}</p>}
          </div>
        </div>
      ))}
    </div>
  )
}
