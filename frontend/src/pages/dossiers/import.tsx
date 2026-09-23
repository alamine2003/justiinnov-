import { useState, type FormEvent } from "react"
import { AlertTriangle, CheckCircle2, FlaskConical, Loader2, Upload } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { FormError } from "@/components/ui/form-error"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { Switch } from "@/components/ui/switch"
import { TruncatedNotice } from "@/components/ui/truncated-notice"
import { fetchCountries } from "@/lib/countries"
import { REFERENTIEL_PAGE_SIZE, invalidateReferentiel, useReferentiel } from "@/lib/referentiel"
import { importExpenses, type ImportError, type ImportResult } from "@/lib/reporting"

/** Rend une erreur de ligne, quelle que soit la forme que le serveur lui donne. */
function decrireErreur(erreur: ImportError | string): { ligne?: number; motif: string } {
  if (typeof erreur === "string") return { motif: erreur }
  return { ligne: erreur.ligne, motif: erreur.motif ?? JSON.stringify(erreur) }
}

/**
 * Import d'un classeur de dépenses (administrateurs).
 *
 * Le pays déclare dans l'application, ligne à ligne ; ce qui entre par un
 * classeur arrive en brouillon et suit ensuite le même circuit. La
 * simulation (`dry_run`) montre ce qui serait créé sans rien écrire : à
 * essayer d'abord.
 */
export function ImportSection() {
  const { t } = useTranslation()
  const [country, setCountry] = useState<number | "">("")
  const [file, setFile] = useState<File | null>(null)
  const [dryRun, setDryRun] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)
  // Réinitialise le champ fichier après un import : la valeur d'un
  // `<input type="file">` ne se pilote pas autrement.
  const [fileKey, setFileKey] = useState(0)

  const countries = useReferentiel("countries", () =>
    fetchCountries({ page_size: REFERENTIEL_PAGE_SIZE, is_active: true }),
  )

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!file) {
      setError(t("configuration.import.fichier_requis"))
      return
    }
    setRunning(true)
    setError(null)
    setResult(null)
    try {
      const resultat = await importExpenses(file, { country, dryRun })
      setResult(resultat)
      if (!resultat.dry_run) {
        setFile(null)
        setFileKey((k) => k + 1)
        // Le classeur crée des équipes, des managers et des dossiers : les
        // listes en cache ne les connaissent pas.
        invalidateReferentiel(
          (key) =>
            key === "teams" ||
            key === "managers" ||
            key === "dossiers" ||
            key.startsWith("country:"),
        )
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : t("configuration.import.impossible"))
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="space-y-4">
      <Alert>
        <Upload className="h-4 w-4" />
        <AlertTitle>{t("configuration.import.titre")}</AlertTitle>
        <AlertDescription>{t("configuration.import.description")}</AlertDescription>
      </Alert>
      {countries.error && (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t("erreurs.referentiel_indisponible")}</AlertTitle>
          <AlertDescription>{countries.error}</AlertDescription>
        </Alert>
      )}
      <TruncatedNotice page={countries.data} noun={t("configuration.pays.noun_pluriel")} />

      <Card className="border-border/60 shadow-sm">
        <CardHeader>
          <CardTitle className="text-sm font-semibold">
            {t("configuration.import.classeur")}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="grid gap-4 sm:grid-cols-2" noValidate>
            <FormError className="sm:col-span-2">{error}</FormError>

            <div className="grid gap-2">
              <Label htmlFor="import-country">{t("commun.pays")}</Label>
              <NativeSelect
                id="import-country"
                value={country}
                onChange={(e) => setCountry(e.target.value === "" ? "" : Number(e.target.value))}
              >
                <option value="">{t("configuration.import.pays_colonne")}</option>
                {(countries.data?.results ?? []).map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.country_ref ? `${c.country_ref} — ` : ""}
                    {c.name}
                  </option>
                ))}
              </NativeSelect>
              <p className="text-xs text-muted-foreground">
                {t("configuration.import.pays_aide")}
              </p>
            </div>

            <div className="grid gap-2">
              <Label htmlFor="import-file">{t("configuration.import.fichier")}</Label>
              <Input
                key={fileKey}
                id="import-file"
                type="file"
                accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                required
              />
              <p className="text-xs text-muted-foreground">
                {t("configuration.import.fichier_aide")}
              </p>
            </div>

            <div className="flex items-center justify-between gap-3 rounded-lg border border-border/60 p-3 sm:col-span-2">
              <div>
                <Label htmlFor="import-dry-run" className="block text-sm font-medium">
                  {t("configuration.import.simulation")}
                </Label>
                <p className="text-xs text-muted-foreground">
                  {t("configuration.import.simulation_aide")}
                </p>
              </div>
              <Switch id="import-dry-run" checked={dryRun} onCheckedChange={setDryRun} />
            </div>

            <div className="sm:col-span-2">
              <Button type="submit" disabled={running}>
                {running ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : dryRun ? (
                  <FlaskConical className="mr-2 h-4 w-4" aria-hidden />
                ) : (
                  <Upload className="mr-2 h-4 w-4" aria-hidden />
                )}
                {dryRun ? t("configuration.import.simuler") : t("configuration.import.importer")}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {result && <ImportResultCard result={result} />}
    </div>
  )
}

function ImportResultCard({ result }: { result: ImportResult }) {
  const { t } = useTranslation()
  const erreurs = result.erreurs ?? []
  const reussi = erreurs.length === 0
  return (
    <Card className="border-border/60 shadow-sm" aria-live="polite">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-semibold">
          {reussi ? (
            <CheckCircle2 className="h-4 w-4" aria-hidden />
          ) : (
            <AlertTriangle className="h-4 w-4 text-destructive" aria-hidden />
          )}
          {result.dry_run
            ? t("configuration.import.resultat_simulation")
            : t("configuration.import.resultat_import")}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <dl className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <Compteur label={t("configuration.import.dossiers_crees")} valeur={result.dossiers_crees ?? 0} />
          <Compteur label={t("configuration.import.lignes_creees")} valeur={result.lignes_creees ?? 0} />
          <Compteur label={t("configuration.import.equipes_creees")} valeur={result.equipes_creees ?? 0} />
          <Compteur label={t("configuration.import.managers_crees")} valeur={result.managers_crees ?? 0} />
        </dl>
        {!reussi && (
          <p className="text-xs text-muted-foreground">
            {t("configuration.import.rien_ecrit")}
          </p>
        )}
        {erreurs.length > 0 && (
          <ul className="space-y-1 rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
            {erreurs.map((erreur, index) => {
              const { ligne, motif } = decrireErreur(erreur)
              return (
                <li key={index}>
                  {ligne !== undefined && (
                    <span className="font-mono text-xs">
                      {t("configuration.import.ligne", { numero: ligne })}
                    </span>
                  )}
                  {ligne !== undefined && t("commun.separateur_libelle")}
                  {motif}
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

function Compteur({ label, valeur }: { label: string; valeur: number }) {
  return (
    <div className="rounded-lg border border-border/60 p-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-2xl font-semibold tracking-tight">{valeur}</dd>
    </div>
  )
}
