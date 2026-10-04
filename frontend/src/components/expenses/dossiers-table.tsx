import { Link } from "react-router-dom"
import { FolderOpen } from "lucide-react"
import { useTranslation } from "react-i18next"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { EmptyRow, SkeletonRows } from "@/components/ui/table-states"
import { StatusBadge } from "@/components/expenses/status-badge"
import type { Dossier } from "@/lib/types"
import { cn, formatAmount, formatDay } from "@/lib/utils"

/**
 * Tableau des dossiers : la liste de tous les dossiers et la fiche d'un
 * projet le partagent. Dans la liste, la deuxième colonne dit le projet,
 * puis vient le pays ; dans un projet, qu'on connaît déjà, elle dit le
 * type du dossier, et le pays — celui du projet — n'est pas répété.
 */
export function DossiersTable({
  dossiers,
  loading,
  colonne,
  vide,
  className,
}: {
  dossiers: Dossier[]
  loading: boolean
  colonne: "projet" | "type"
  /** Phrase de l'état vide : ce qu'il faut faire, déjà traduite. */
  vide: string
  /** Pour une liste à hauteur d'écran : `defile` (DESIGN.md, « Hauteur d'écran »). */
  className?: string
}) {
  const { t } = useTranslation()
  // Dans un projet, le pays est celui du projet : la colonne le répéterait.
  const colonnes = colonne === "projet" ? 9 : 8
  return (
    <div className={cn("overflow-x-auto rounded-lg border border-border/60", className)}>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead scope="col">{t("dossiers.liste.colonnes.numero")}</TableHead>
            <TableHead scope="col">
              {colonne === "projet" ? t("champs.project") : t("projets.type_de_dossier")}
            </TableHead>
            {colonne === "projet" && <TableHead scope="col">{t("commun.pays")}</TableHead>}
            <TableHead scope="col">{t("commun.date")}</TableHead>
            <TableHead scope="col" className="text-center">{t("dossiers.liste.colonnes.lignes")}</TableHead>
            <TableHead scope="col" className="text-center">{t("dossiers.liste.colonnes.preuves")}</TableHead>
            <TableHead scope="col" className="text-right">{t("dossiers.liste.colonnes.depenses")}</TableHead>
            <TableHead scope="col" className="text-right">{t("dossiers.liste.colonnes.ecart")}</TableHead>
            <TableHead scope="col">{t("commun.statut")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading ? (
            <SkeletonRows columns={colonnes} />
          ) : dossiers.length === 0 ? (
            <EmptyRow colSpan={colonnes} icon={FolderOpen} title={t("dossiers.liste.vide.titre")} hint={vide} />
          ) : (
            dossiers.map((dossier) => (
              <TableRow key={dossier.id}>
                <TableCell>
                  {/* Le lien porte la navigation : accessible au clavier,
                      ouvrable dans un nouvel onglet. */}
                  <Link
                    to={`/dossiers/${dossier.id}`}
                    className="font-medium hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {dossier.number}
                  </Link>
                  <p className="text-xs text-muted-foreground">{dossier.label}</p>
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {colonne === "projet" ? (
                    dossier.project ? (
                      <Link
                        to={`/projets/${dossier.project}`}
                        className="hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      >
                        {dossier.project_name}
                      </Link>
                    ) : (
                      t("commun.aucun")
                    )
                  ) : (
                    dossier.kind_name ?? t("projets.sans_type")
                  )}
                </TableCell>
                {colonne === "projet" && (
                  <TableCell className="text-muted-foreground">
                    {dossier.country_ref ?? dossier.country_name}
                  </TableCell>
                )}
                <TableCell className="text-muted-foreground">{formatDay(dossier.date)}</TableCell>
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
  )
}
