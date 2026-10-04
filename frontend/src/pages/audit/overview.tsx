import type { ReactNode } from "react"
import { Link } from "react-router-dom"
import { AlertTriangle, ShieldAlert } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { BarresParJour, Legende } from "@/components/ui/charts"
import { StatCard } from "@/components/ui/stat-card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Evenement } from "@/components/audit/evenement"
import { fetchAuditSynthese } from "@/lib/expenses"
import type { SyntheseAudit } from "@/lib/types"
import { useQuery } from "@/lib/use-query"
import { formatDay } from "@/lib/utils"
import { BarreDePeriode } from "./barre-de-periode"
import { bornes, useFiltresAudit } from "./use-filtres"

type Compteur = keyof SyntheseAudit["compteurs"]

/**
 * Les tuiles de la vue d'ensemble, et l'onglet filtré qu'ouvre chacune.
 * Les chiffres viennent tous du serveur (décision 111) : la page ne
 * compte rien. Une tuile n'a de lien que si un filtre du journal reproduit
 * exactement son compte (`expenses.synthese_audit.COMPTEURS_CIRCUIT`) :
 * « Lignes tranchées », « Refus » et « Justificatifs déposés » réunissent
 * plusieurs actions, elles restent sans lien plutôt que d'ouvrir une liste
 * qui ne dirait pas le même chiffre.
 */
const TUILES_CIRCUIT: { cle: Compteur; filtre?: Record<string, string>; sensible?: boolean }[] = [
  { cle: "declarations", filtre: { action: "submitted", object_type: "Dossier" } },
  { cle: "decisions" },
  { cle: "reouvertures", filtre: { action: "reopened", object_type: "Dossier" }, sensible: true },
  { cle: "rectifications", filtre: { action: "rectification_requested" }, sensible: true },
  { cle: "refus", sensible: true },
  { cle: "pieces" },
  { cle: "renommages", filtre: { action: "renamed" } },
  { cle: "suppressions", filtre: { action: "deleted" }, sensible: true },
  { cle: "imports", filtre: { action: "imported" } },
  { cle: "sorties", filtre: { action: "downloaded" }, sensible: true },
]

const TUILES_REFERENTIEL: { cle: Compteur; filtre: Record<string, string>; sensible?: boolean }[] = [
  { cle: "changements_de_droits", filtre: { model_name: "workflow_configuration" }, sensible: true },
  { cle: "echecs_de_connexion", filtre: { action: "login_failed" }, sensible: true },
  { cle: "reinitialisations_2fa", filtre: { action: "totp_reset" }, sensible: true },
  { cle: "desactivations", filtre: { action: "deactivated" } },
  { cle: "projets", filtre: { model_name: "project" } },
]

/** Une tuile qui mène au journal déjà filtré : un lien, pas une carte cliquable. */
function Tuile({ to, children }: { to?: string; children: ReactNode }) {
  if (!to) return <>{children}</>
  return (
    <Link
      to={to}
      className="block rounded-xl transition-colors hover:bg-accent/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {children}
    </Link>
  )
}

export function VueDEnsemble() {
  const { t } = useTranslation()
  const { lire, changer } = useFiltresAudit()
  const filtres = bornes(lire)

  const query = useQuery(
    `audit-synthese:${JSON.stringify(filtres)}`,
    (signal) => fetchAuditSynthese(filtres, signal),
    { fallback: t("audit.synthese.indisponible") },
  )
  const synthese = query.data

  /**
   * L'adresse du journal filtré : la période est celle que le serveur a
   * comptée — les trente derniers jours quand l'adresse n'en dit rien —,
   * pour que la liste ouverte dise le même chiffre que la tuile.
   */
  const lien = (onglet: string, filtre: Record<string, string>) =>
    `/audit?${new URLSearchParams({
      ...filtres,
      ...(synthese ? { debut: synthese.debut, fin: synthese.fin } : {}),
      onglet,
      ...filtre,
    }).toString()}`

  return (
    <div className="space-y-6">
      <BarreDePeriode lire={lire} changer={changer} />

      {query.error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("commun.erreur")}</AlertTitle>
          <AlertDescription>{query.error}</AlertDescription>
        </Alert>
      )}

      {synthese && (
        <>
          <p className="text-sm text-muted-foreground">
            {t("audit.synthese.periode", {
              debut: formatDay(synthese.debut),
              fin: formatDay(synthese.fin),
              circuit: synthese.compteurs.circuit,
              referentiel: synthese.compteurs.referentiel,
            })}
          </p>

          <section aria-labelledby="audit-tuiles-circuit" className="space-y-2">
            <h3 id="audit-tuiles-circuit" className="text-sm font-semibold">
              {t("audit.source.circuit")}
            </h3>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              {TUILES_CIRCUIT.map(({ cle, filtre, sensible }) => (
                <Tuile key={cle} to={filtre && lien("circuit", filtre)}>
                  <StatCard
                    label={t(`audit.synthese.compteurs.${cle}`)}
                    value={synthese.compteurs[cle]}
                    tone={sensible && synthese.compteurs[cle] > 0 ? "danger" : undefined}
                  />
                </Tuile>
              ))}
            </div>
          </section>

          <section aria-labelledby="audit-tuiles-referentiel" className="space-y-2">
            <h3 id="audit-tuiles-referentiel" className="text-sm font-semibold">
              {t("audit.source.referentiel")}
            </h3>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
              {TUILES_REFERENTIEL.map(({ cle, filtre, sensible }) => (
                <Tuile key={cle} to={lien("referentiel", filtre)}>
                  <StatCard
                    label={t(`audit.synthese.compteurs.${cle}`)}
                    value={synthese.compteurs[cle]}
                    tone={sensible && synthese.compteurs[cle] > 0 ? "danger" : undefined}
                  />
                </Tuile>
              ))}
            </div>
          </section>

          <Card className="border-border/60 shadow-sm">
            <CardHeader>
              <CardTitle className="text-sm">{t("audit.synthese.par_jour")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {synthese.par_jour.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("audit.synthese.rien")}</p>
              ) : (
                <>
                  <Legende
                    items={[
                      { tone: "bg-marque", label: t("audit.source.circuit") },
                      { tone: "bg-marque-clair", label: t("audit.source.referentiel") },
                    ]}
                  />
                  <BarresParJour jours={synthese.par_jour} title={t("audit.synthese.par_jour")} />
                  {/* Les chiffres en texte, comme sous chaque graphique (DESIGN.md). */}
                  <details className="text-xs">
                    <summary className="cursor-pointer text-muted-foreground">
                      {t("audit.synthese.detail_par_jour")}
                    </summary>
                    <ul className="mt-2 grid gap-1 sm:grid-cols-2 lg:grid-cols-3">
                      {synthese.par_jour.map((jour) => (
                        <li key={jour.jour}>
                          {t("audit.synthese.jour", {
                            jour: formatDay(jour.jour),
                            circuit: jour.circuit,
                            referentiel: jour.referentiel,
                          })}
                        </li>
                      ))}
                    </ul>
                  </details>
                </>
              )}
            </CardContent>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card className="border-border/60 shadow-sm">
              <CardHeader>
                <CardTitle className="text-sm">{t("audit.synthese.par_utilisateur")}</CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead scope="col">{t("audit.col_utilisateur")}</TableHead>
                      <TableHead scope="col" className="text-right">{t("audit.synthese.evenements")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {synthese.par_utilisateur.map((ligne) => (
                      <TableRow key={ligne.user}>
                        <TableCell>
                          <Link to={lien("circuit", { user: ligne.user })} className="font-medium hover:underline">
                            {ligne.user}
                          </Link>
                        </TableCell>
                        <TableCell className="text-right tabular-nums">{ligne.count}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
            <Card className="border-border/60 shadow-sm">
              <CardHeader>
                <CardTitle className="text-sm">{t("audit.synthese.par_pays")}</CardTitle>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead scope="col">{t("commun.pays")}</TableHead>
                      <TableHead scope="col" className="text-right">{t("audit.synthese.evenements")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {synthese.par_pays.map((ligne) => (
                      <TableRow key={ligne.country}>
                        <TableCell>{ligne.name}</TableCell>
                        <TableCell className="text-right tabular-nums">{ligne.count}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </div>

          <section aria-labelledby="audit-a-surveiller" className="space-y-2">
            <h3 id="audit-a-surveiller" className="flex items-center gap-2 text-sm font-semibold">
              <ShieldAlert className="h-4 w-4 text-statut-attente" aria-hidden />
              {t("audit.synthese.a_surveiller")}
            </h3>
            <p className="text-xs text-muted-foreground">{t("audit.synthese.a_surveiller_aide")}</p>
            {synthese.a_surveiller.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("audit.synthese.rien_a_surveiller")}</p>
            ) : (
              <ol className="space-y-2">
                {synthese.a_surveiller.map((entree) => (
                  <Evenement key={`${entree.source}-${entree.id}`} entree={entree} />
                ))}
              </ol>
            )}
          </section>
        </>
      )}
    </div>
  )
}
