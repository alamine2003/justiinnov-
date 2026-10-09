import { Fragment, useState } from "react"
import { AlertTriangle, ChevronDown, ChevronRight, Download, Loader2, Search, Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { FormError } from "@/components/ui/form-error"
import { Input } from "@/components/ui/input"
import { NativeSelect } from "@/components/ui/native-select"
import { PageHeader } from "@/components/ui/page-header"
import { PAGE_SIZE, Pagination } from "@/components/ui/pagination"
import { EmptyRow, SkeletonRows } from "@/components/ui/table-states"
import { TruncatedNotice } from "@/components/ui/truncated-notice"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useAuth } from "@/context/use-auth"
import { fetchCorbeille, telechargerDepuisLaCorbeille } from "@/lib/corbeille"
import { fetchCountries } from "@/lib/countries"
import { REFERENTIEL_PAGE_SIZE, isTruncated, useReferentiel } from "@/lib/referentiel"
import type { ElementSupprime, NatureSupprimee } from "@/lib/types"
import { useDebouncedValue } from "@/lib/use-debounced"
import { useQuery } from "@/lib/use-query"
import { formatAmount, formatDate } from "@/lib/utils"

/** Les natures, pour le filtre ; chaque entrée affiche le libellé du serveur. */
const NATURES: NatureSupprimee[] = ["projet", "dossier", "ligne", "piece"]

const COLONNES = 7

/**
 * La corbeille du super administrateur (décision 120), lue par la RH et la
 * direction (`audit.read`) : ce qui a été retiré avant la mise en ligne
 * finale, avec qui, quand et pourquoi. La liste montre ce qui a été choisi ;
 * chaque élément se déplie sur ce qu'il a emporté. Rien ne s'y modifie ni
 * ne s'y supprime ; un justificatif gardé se télécharge.
 */
export function CorbeillePage() {
  const { t } = useTranslation()
  const { me } = useAuth()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState("")
  const [nature, setNature] = useState("")
  const [pays, setPays] = useState("")
  const [ouvert, setOuvert] = useState<number | null>(null)
  const [erreur, setErreur] = useState<string | null>(null)
  const debouncedSearch = useDebouncedValue(search)
  const countries = useReferentiel("countries", () =>
    fetchCountries({ page_size: REFERENTIEL_PAGE_SIZE, is_active: true }),
  )

  const filtres: Record<string, unknown> = { tetes: true }
  if (nature) filtres.nature = nature
  if (pays) filtres.country = pays
  if (debouncedSearch) filtres.search = debouncedSearch
  const query = useQuery(
    `corbeille:${JSON.stringify({ page, filtres })}`,
    (signal) => fetchCorbeille({ ...filtres, page, page_size: PAGE_SIZE }, signal),
    { fallback: t("corbeille.page.indisponible") },
  )
  const elements = query.data?.results ?? []
  const filtree = Boolean(nature || pays || debouncedSearch)
  const count = query.data?.count ?? 0

  return (
    <div className="space-y-6 court:space-y-3">
      <PageHeader title={t("corbeille.page.titre")} description={t("corbeille.page.description")} />

      <Alert variant={me?.workflow.suppressions_ouvertes ? "destructive" : "default"}>
        <Trash2 className="h-4 w-4" />
        <AlertDescription>
          {me?.workflow.suppressions_ouvertes ? t("corbeille.page.ouverte") : t("corbeille.page.fermee")}
        </AlertDescription>
      </Alert>

      {query.error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("commun.erreur")}</AlertTitle>
          <AlertDescription>{query.error}</AlertDescription>
        </Alert>
      )}
      <FormError>{erreur}</FormError>

      <div className="flex flex-col flex-wrap gap-3 sm:flex-row sm:items-center">
        <div className="relative w-full sm:max-w-xs">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
          <Input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value)
              setPage(1)
            }}
            placeholder={t("corbeille.page.recherche_placeholder")}
            aria-label={t("corbeille.page.recherche_aria")}
            className="pl-9"
          />
        </div>
        <NativeSelect
          value={nature}
          onChange={(e) => {
            setNature(e.target.value)
            setPage(1)
          }}
          className="sm:max-w-[14rem]"
          aria-label={t("corbeille.page.nature_aria")}
        >
          <option value="">{t("corbeille.page.toutes_natures")}</option>
          {NATURES.map((valeur) => (
            <option key={valeur} value={valeur}>
              {t(`corbeille.natures.${valeur}`)}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          value={pays}
          onChange={(e) => {
            setPays(e.target.value)
            setPage(1)
          }}
          className="sm:max-w-[14rem]"
          aria-label={t("commun.pays")}
        >
          <option value="">{t("dossiers.liste.tous_pays")}</option>
          {(countries.data?.results ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </NativeSelect>
      </div>

      <Card className="border-border/60 shadow-sm">
        <CardContent>
          <div className="overflow-x-auto rounded-lg border border-border/60">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">{t("corbeille.page.col_date")}</TableHead>
                  <TableHead scope="col">{t("corbeille.page.col_element")}</TableHead>
                  <TableHead scope="col">{t("corbeille.page.col_pays")}</TableHead>
                  <TableHead scope="col" className="text-right">{t("corbeille.page.col_montant")}</TableHead>
                  <TableHead scope="col">{t("corbeille.page.col_par")}</TableHead>
                  <TableHead scope="col">{t("corbeille.page.col_motif")}</TableHead>
                  <TableHead scope="col" className="text-right">{t("corbeille.page.col_actions")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.loading ? (
                  <SkeletonRows columns={COLONNES} />
                ) : elements.length === 0 ? (
                  // Sous un filtre, la corbeille n'est pas vide : rien ne correspond.
                  <EmptyRow
                    colSpan={COLONNES}
                    icon={Trash2}
                    title={filtree ? t("corbeille.page.aucun_titre") : t("corbeille.page.vide_titre")}
                    hint={filtree ? t("corbeille.page.aucun_aide") : t("corbeille.page.vide_aide")}
                  />
                ) : (
                  elements.map((element) => (
                    <Fragment key={element.id}>
                      <LigneDeCorbeille
                        element={element}
                        deplie={ouvert === element.id}
                        onDeplier={
                          element.emportes > 0
                            ? () => setOuvert((courant) => (courant === element.id ? null : element.id))
                            : undefined
                        }
                        onErreur={setErreur}
                      />
                      {ouvert === element.id && <Emportes racine={element} onErreur={setErreur} />}
                    </Fragment>
                  ))
                )}
              </TableBody>
            </Table>
          </div>

          <Pagination
            page={page}
            count={count}
            onChange={setPage}
            noun={[t("corbeille.page.noun_singulier"), t("corbeille.page.noun_pluriel")]}
          />
        </CardContent>
      </Card>
    </div>
  )
}

/** Ce qu'un élément a emporté, lu à la demande, sous sa ligne. */
function Emportes({
  racine,
  onErreur,
}: {
  racine: ElementSupprime
  onErreur: (message: string | null) => void
}) {
  const { t } = useTranslation()
  const query = useQuery(
    `corbeille:emportes:${racine.id}`,
    // D'un bloc, comme les listes du référentiel ; au-delà, l'avis le dit.
    // Dans l'ordre du retrait : chaque dossier, puis ses lignes.
    (signal) => fetchCorbeille({ racine: racine.id, ordering: "id", page_size: REFERENTIEL_PAGE_SIZE }, signal),
    { fallback: t("corbeille.page.indisponible") },
  )
  if (query.loading) return <SkeletonRows columns={COLONNES} rows={2} />
  if (query.error) {
    return (
      <TableRow>
        <TableCell colSpan={COLONNES}>
          <FormError>{query.error}</FormError>
        </TableCell>
      </TableRow>
    )
  }
  return (
    <>
      {(query.data?.results ?? []).map((element) => (
        <LigneDeCorbeille key={element.id} element={element} emporte onErreur={onErreur} />
      ))}
      {isTruncated(query.data) && (
        <TableRow>
          <TableCell colSpan={COLONNES}>
            <TruncatedNotice page={query.data} noun={t("corbeille.page.noun_pluriel")} />
          </TableCell>
        </TableRow>
      )}
    </>
  )
}

function LigneDeCorbeille({
  element,
  emporte = false,
  deplie = false,
  onDeplier,
  onErreur,
}: {
  element: ElementSupprime
  /** Parti avec un autre : en retrait, sans motif répété. */
  emporte?: boolean
  deplie?: boolean
  onDeplier?: () => void
  onErreur: (message: string | null) => void
}) {
  const { t } = useTranslation()
  const [telechargement, setTelechargement] = useState(false)
  const nom = element.libelle || element.reference

  const telecharger = async () => {
    setTelechargement(true)
    onErreur(null)
    try {
      await telechargerDepuisLaCorbeille(element)
    } catch (e) {
      onErreur(e instanceof Error ? e.message : t("corbeille.page.telechargement_impossible"))
    } finally {
      setTelechargement(false)
    }
  }

  return (
    <TableRow className={emporte ? "bg-muted/40" : undefined}>
      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
        {formatDate(element.supprime_le)}
      </TableCell>
      <TableCell className={emporte ? "pl-8" : undefined}>
        <div className="flex items-start gap-2">
          {onDeplier && (
            <Button
              variant="ghost"
              size="icon"
              className="-ml-1 h-6 w-6 shrink-0"
              aria-expanded={deplie}
              aria-label={
                deplie
                  ? t("corbeille.page.masquer_emportes", { libelle: nom })
                  : t("corbeille.page.voir_emportes", { libelle: nom })
              }
              onClick={onDeplier}
            >
              {deplie ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            </Button>
          )}
          <div className="min-w-0">
            <p className="text-sm font-medium">{element.libelle || element.reference}</p>
            <p className="text-xs text-muted-foreground">
              <Badge variant="outline" className="mr-1 align-middle">
                {element.nature_display}
              </Badge>
              {element.reference && element.reference !== element.libelle && (
                <span className="font-mono">{element.reference}</span>
              )}
              {element.emportes > 0 &&
                ` · ${t("corbeille.page.emportes", { count: element.emportes })}`}
            </p>
          </div>
        </div>
      </TableCell>
      <TableCell className="text-sm">{element.country_name}</TableCell>
      <TableCell className="whitespace-nowrap text-right text-sm tabular-nums">
        {element.montant === null ? "" : formatAmount(element.montant, element.devise)}
      </TableCell>
      <TableCell className="text-sm">{element.supprime_par}</TableCell>
      <TableCell className="max-w-xs text-sm text-muted-foreground">
        {emporte ? "" : element.motif}
      </TableCell>
      <TableCell className="text-right">
        {element.download_url && (
          <Button
            variant="ghost"
            size="icon"
            aria-label={t("corbeille.page.telecharger", { libelle: nom })}
            disabled={telechargement}
            onClick={() => void telecharger()}
          >
            {telechargement ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
          </Button>
        )}
      </TableCell>
    </TableRow>
  )
}
