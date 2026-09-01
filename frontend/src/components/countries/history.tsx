import { useCallback, useEffect, useState } from "react"
import { History } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { fetchHistory } from "@/lib/countries"
import type { ChangeLogEntry } from "@/lib/types"
import { formatDate } from "@/lib/utils"

const ACTION_COLOR: Record<string, string> = {
  created: "bg-emerald-500 hover:bg-emerald-500",
  updated: "bg-blue-500 hover:bg-blue-500",
  reassigned: "bg-amber-500 hover:bg-amber-500",
  deactivated: "bg-zinc-500 hover:bg-zinc-500",
  reactivated: "bg-emerald-500 hover:bg-emerald-500",
  deleted: "bg-destructive hover:bg-destructive",
}

const ACTION_LABEL: Record<string, string> = {
  created: "Création",
  updated: "Mise à jour",
  reassigned: "Rattachement",
  deactivated: "Désactivation",
  reactivated: "Réactivation",
  deleted: "Suppression",
}

export function CaretHistory({ countryId }: { countryId: number }) {
  const [entries, setEntries] = useState<ChangeLogEntry[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchHistory({ country: countryId, page_size: 100 })
      setEntries(data.results)
    } finally {
      setLoading(false)
    }
  }, [countryId])

  useEffect(() => {
    load()
  }, [load])

  if (loading) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-14 animate-pulse rounded-lg bg-muted" />
        ))}
      </div>
    )
  }

  if (entries.length === 0) {
    return (
      <Card className="flex flex-col items-center justify-center gap-2 border-dashed border-border/60 p-10 text-center">
        <History className="h-8 w-8 text-muted-foreground/60" />
        <p className="text-sm font-medium">Aucun historique</p>
        <p className="text-xs text-muted-foreground">
          Les changements de rattachement et de configuration apparaîtront ici.
        </p>
      </Card>
    )
  }

  return (
    <div className="space-y-2">
      {entries.map((entry) => (
        <div
          key={entry.id}
          className="flex items-start justify-between gap-4 rounded-lg border border-border/60 p-4 shadow-sm transition-colors hover:bg-accent/30"
        >
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Badge className={ACTION_COLOR[entry.action] ?? "bg-secondary"}>
                {ACTION_LABEL[entry.action] ?? entry.action_display}
              </Badge>
              <span className="font-medium">{entry.label}</span>
            </div>
            <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
              {entry.model_name_display}
              {entry.from_value ? ` · de : ${entry.from_value}` : ""}
              {entry.from_value && entry.to_value ? " → " : ""}
              {entry.action === "reassigned" ? entry.to_value : ""}
            </p>
          </div>
          <div className="shrink-0 text-right text-xs text-muted-foreground">
            <p>{formatDate(entry.created_at)}</p>
            {entry.performed_by && <p className="font-medium">par {entry.performed_by}</p>}
          </div>
        </div>
      ))}
    </div>
  )
}