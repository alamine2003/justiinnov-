import { Link } from "react-router-dom"
import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
import { DiffList } from "@/components/countries/history"
import { ACTION_STYLE } from "@/lib/status-styles"
import type { EntreeHistorique } from "@/lib/types"
import { formatDate } from "@/lib/utils"

/** Les champs d'un avant et d'un après, champ par champ, pour `DiffList`. */
function enDiff(entree: EntreeHistorique): Record<string, [unknown, unknown]> | null {
  const avant = (entree.avant ?? {}) as Record<string, unknown>
  const apres = (entree.apres ?? {}) as Record<string, unknown>
  const champs = [...new Set([...Object.keys(avant), ...Object.keys(apres)])]
  if (champs.length === 0) return null
  return Object.fromEntries(champs.map((champ) => [champ, [avant[champ], apres[champ]]]))
}

/**
 * Un événement d'un journal, en clair (décisions 110 et 111) : qui, quoi,
 * quand, depuis quelle adresse, sur quel objet, pourquoi — le motif d'abord,
 * puis la note et l'avant / après. Tout vient du serveur, rien ne se
 * déduit ici. Partagé par l'historique d'un projet et la liste
 * « À surveiller » de l'audit.
 */
export function Evenement({ entree }: { entree: EntreeHistorique }) {
  const { t } = useTranslation()
  const diff = enDiff(entree)
  // Le circuit nomme ses objets par leur classe (« Expense ») : on les
  // traduit ; le référentiel les nomme déjà, traduits par le serveur.
  const typeDObjet =
    entree.source === "circuit"
      ? t(`audit.objet.${entree.objet}` as "audit.objet.Dossier", { defaultValue: entree.objet })
      : entree.objet
  const objet = (
    <>
      {entree.label || typeDObjet}
      {entree.object_id != null && (
        <span className="ml-1 text-xs text-muted-foreground">
          {t("audit.evenement.numero", { type: typeDObjet, id: entree.object_id })}
        </span>
      )}
    </>
  )
  return (
    <li className="flex items-start justify-between gap-4 rounded-lg border border-border/60 p-4 shadow-sm">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Badge className={ACTION_STYLE[entree.action] ?? "bg-secondary"}>
            {entree.action_display}
          </Badge>
          <span className="text-xs text-muted-foreground">
            {entree.source === "circuit" ? t("audit.source.circuit") : t("audit.source.referentiel")}
          </span>
          <span className="font-medium">
            {entree.source === "circuit" && entree.objet === "Dossier" && entree.object_id != null ? (
              <Link to={`/dossiers/${entree.object_id}`} className="hover:underline">
                {objet}
              </Link>
            ) : (
              objet
            )}
          </span>
        </div>
        {entree.motif && (
          <p className="mt-1 text-sm">
            <span className="font-medium">{t("audit.evenement.motif")}</span> {entree.motif}
          </p>
        )}
        {entree.note && (
          <p className="mt-1 text-sm text-muted-foreground">
            <span className="font-medium">{t("audit.evenement.note")}</span> {entree.note}
          </p>
        )}
        {diff && <DiffList diff={diff} />}
      </div>
      <div className="shrink-0 text-right text-xs text-muted-foreground">
        <p>{formatDate(entree.created_at)}</p>
        {entree.user && <p className="font-medium">{t("pays.historique.par", { nom: entree.user })}</p>}
        {entree.ip_address && <p className="font-mono">{entree.ip_address}</p>}
      </div>
    </li>
  )
}
