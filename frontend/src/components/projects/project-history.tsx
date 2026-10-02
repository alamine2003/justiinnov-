import { History } from "lucide-react"
import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Card } from "@/components/ui/card"
import { FormError } from "@/components/ui/form-error"
import { Evenement } from "@/components/audit/evenement"
import { fetchProjectHistory } from "@/lib/countries"
import { useQuery } from "@/lib/use-query"

/**
 * L'historique d'un projet (décision 110) : le projet, ses dossiers, leurs
 * lignes et leurs pièces, en une seule chronologie, du plus récent au plus
 * ancien. Lu avec `audit.read` : il relit le journal d'audit.
 */
export function ProjectHistory({ projectId }: { projectId: number }) {
  const { t } = useTranslation()
  const query = useQuery(
    `historique-projet:${projectId}`,
    (signal) => fetchProjectHistory(projectId, signal),
    { fallback: t("projets.historique_onglet.indisponible") },
  )
  const entrees = query.data?.entrees ?? []

  if (query.loading && !query.data) {
    return (
      <div className="space-y-3" aria-busy="true">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-16 animate-pulse rounded-lg bg-muted" />
        ))}
      </div>
    )
  }

  if (query.error) return <FormError>{query.error}</FormError>

  if (entrees.length === 0) {
    return (
      <Card className="flex flex-col items-center justify-center gap-2 border-dashed border-border/60 p-10 text-center">
        <History className="h-8 w-8 text-muted-foreground/60" aria-hidden />
        <p className="text-sm font-medium">{t("projets.historique_onglet.vide")}</p>
      </Card>
    )
  }

  return (
    <div className="space-y-2">
      {query.data?.tronque && (
        <Alert>
          <AlertDescription>
            {t("projets.historique_onglet.tronque")}{" "}
            <Link to={`/audit?onglet=circuit&projet=${projectId}`} className="font-medium underline">
              {t("projets.historique_onglet.journal_complet")}
            </Link>
          </AlertDescription>
        </Alert>
      )}
      <ol className="space-y-2">
        {entrees.map((entree) => (
          <Evenement key={`${entree.source}-${entree.id}`} entree={entree} />
        ))}
      </ol>
    </div>
  )
}
