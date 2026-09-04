import { useState, type FormEvent } from "react"
import { useSearchParams } from "react-router-dom"
import { AlertTriangle, CheckCircle2, Info, Loader2, Lock, Save } from "lucide-react"
import { useTranslation } from "react-i18next"
import type { TFunction } from "i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { PageHeader } from "@/components/ui/page-header"
import { Button } from "@/components/ui/button"
import { FormError } from "@/components/ui/form-error"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { CountriesSection } from "@/pages/configuration/countries-section"
import { ImportSection } from "@/pages/configuration/import-section"
import { RatesSection } from "@/pages/configuration/rates-section"
import { UsersSection } from "@/pages/configuration/users-section"
import { useAuth } from "@/context/use-auth"
import {
  fetchConfiguration,
  fetchPermissionMatrix,
  updateWorkflowConfiguration,
} from "@/lib/accounts"
import { ApiError, type FieldErrors } from "@/lib/api"
import { BRAND } from "@/lib/brand"
import { OVERRUN_POLICIES, overrunPolicyLabel } from "@/lib/labels"
import { invalidateReferentiel } from "@/lib/referentiel"
import { STATUS_TONES } from "@/lib/status-styles"
import { type OverrunPolicy, type WorkflowConfiguration } from "@/lib/types"
import { useQuery } from "@/lib/use-query"
import { normalizeDecimal } from "@/lib/utils"

/**
 * Identifiants d'onglets : valeurs techniques, reprises dans l'URL
 * (`?onglet=utilisateurs`). Seuls les libellés sont traduits.
 */
const ONGLETS = ["general", "utilisateurs", "pays", "permissions", "import"] as const

export function ConfigurationPage() {
  const { t } = useTranslation()
  const { can } = useAuth()
  // L'onglet vit dans l'URL : un lien vers « Configuration › Permissions »
  // doit rouvrir cet onglet, pas le premier.
  const [params, setParams] = useSearchParams()
  const onglet = params.get("onglet") ?? "general"
  // L'import manipule des fichiers : réservé, comme les exports, aux
  // administrateurs (`export_data`).
  const onglets = ONGLETS.filter((value) => value !== "import" || can("export_data"))

  return (
    <div className="space-y-6">
      <PageHeader
        title={t("configuration.titre")}
        description={t("configuration.description")}
      />

      <Tabs
        value={onglet}
        onValueChange={(value) => setParams({ onglet: value })}
      >
        <TabsList className="flex w-full flex-wrap justify-start bg-muted/60">
          {onglets.map((value) => (
            <TabsTrigger key={value} value={value}>
              {t(`configuration.onglets.${value}`)}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="general" className="mt-4">
          <GeneralSection />
        </TabsContent>
        <TabsContent value="utilisateurs" className="mt-4">
          <UsersSection />
        </TabsContent>
        <TabsContent value="pays" className="mt-4">
          <CountriesSection />
        </TabsContent>
        <TabsContent value="permissions" className="mt-4">
          <PermissionsSection />
        </TabsContent>
        {can("export_data") && (
          <TabsContent value="import" className="mt-4">
            <ImportSection />
          </TabsContent>
        )}
      </Tabs>
    </div>
  )
}

function GeneralSection() {
  const { t } = useTranslation()
  const query = useQuery("configuration:page", () => fetchConfiguration())
  const config = query.data

  if (query.loading && !config) return <Chargement />
  if (query.error && !config) return <Erreur message={query.error} />
  if (!config) return null

  return (
    <div className="space-y-4">
      <Alert>
        <Info className="h-4 w-4" />
        <AlertTitle>{t("configuration.general.parametres_titre")}</AlertTitle>
        <AlertDescription>{t("configuration.general.parametres_texte")}</AlertDescription>
      </Alert>

      <div className="grid gap-4 lg:grid-cols-2">
        <Bloc titre={t("configuration.general.application")}>
          <Ligne label={t("commun.nom")} valeur={BRAND.name} />
          <Ligne label={t("layout.version")} valeur={BRAND.version} />
          <Ligne label={t("configuration.general.developpement")} valeur={BRAND.developer} />
          <Ligne
            label={t("configuration.general.fuseau_serveur")}
            valeur={config.systeme.fuseau}
          />
          <Ligne
            label={t("configuration.general.mode_debug")}
            valeur={
              config.systeme.mode_debug
                ? t("configuration.general.active")
                : t("commun.desactive")
            }
            alerte={config.systeme.mode_debug}
          />
        </Bloc>

        <Bloc titre={t("configuration.general.alertes")}>
          <Ligne
            label={t("configuration.general.seuils_consommation")}
            valeur={config.alertes.seuils
              .map((s) => t("configuration.general.seuil_pourcent", { valeur: s }))
              .join(" · ")}
          />
          <Ligne
            label={t("configuration.general.depense_inhabituelle")}
            valeur={t("configuration.general.depense_inhabituelle_valeur", {
              facteur: config.alertes.facteur_depense_inhabituelle,
            })}
          />
        </Bloc>

        <Bloc titre={t("configuration.general.justificatifs")}>
          <Ligne
            label={t("configuration.general.stockage")}
            valeur={config.justificatifs.stockage}
          />
          <Ligne
            label={t("configuration.general.taille_max")}
            valeur={t("configuration.general.taille_max_valeur", {
              taille: config.justificatifs.taille_max_mo,
            })}
          />
          <Ligne
            label={t("configuration.general.formats")}
            valeur={config.justificatifs.formats_acceptes.join(" ")}
          />
        </Bloc>

        <Bloc titre={t("configuration.general.budget_notifications")}>
          <Ligne
            label={t("configuration.general.devise_consolidation")}
            valeur={config.budget.devise_de_consolidation}
          />
          <Ligne
            label={t("configuration.general.envoi_emails")}
            valeur={
              config.notifications.email_configure
                ? t("configuration.general.smtp_configure")
                : t("configuration.general.smtp_absent")
            }
            alerte={!config.notifications.email_configure}
          />
          <Ligne
            label={t("configuration.general.expediteur")}
            valeur={config.notifications.expediteur}
          />
        </Bloc>
      </div>

      <WorkflowForm
        key={JSON.stringify(config.workflow)}
        workflow={config.workflow}
        onSaved={(workflow) => {
          query.setData((current) => (current ? { ...current, workflow } : current))
          // Les autres écrans (formulaire d'enveloppe, dépôt de pièce) lisent
          // la configuration en cache.
          invalidateReferentiel("configuration")
        }}
      />

      <RatesSection />
    </div>
  )
}

interface WorkflowDraft {
  require_review_step: boolean
  warn_without_proof_submission: boolean
  unjustified_alert_days: string
  unusual_expense_factor: string
  alert_thresholds: string
  default_overrun_policy: OverrunPolicy
}

/** Valide la saisie et la traduit pour le serveur ; renvoie les erreurs par champ sinon. */
function validateWorkflow(
  t: TFunction,
  draft: WorkflowDraft,
): {
  values?: Partial<WorkflowConfiguration>
  errors: FieldErrors
} {
  const errors: FieldErrors = {}
  const jours = Number(draft.unjustified_alert_days.trim())
  if (draft.unjustified_alert_days.trim() === "" || !Number.isInteger(jours) || jours < 0) {
    errors.unjustified_alert_days = [t("configuration.workflow.jours_invalides")]
  }
  const facteur = normalizeDecimal(draft.unusual_expense_factor)
  if (facteur === null || Number(facteur) <= 0) {
    errors.unusual_expense_factor = [t("configuration.workflow.facteur_invalide")]
  }
  // Chaque seuil est vérifié ; un « abc » ou un « -5 » est signalé au lieu
  // d'être filtré en silence — ce qui laissait croire qu'il avait été retenu.
  const seuils: number[] = []
  const invalides: string[] = []
  for (const brut of draft.alert_thresholds.split(",")) {
    const texte = brut.trim()
    if (texte === "") continue
    const valeur = Number(texte)
    if (!Number.isInteger(valeur) || valeur < 0 || valeur > 1000) invalides.push(texte)
    else seuils.push(valeur)
  }
  if (invalides.length > 0) {
    errors.alert_thresholds = [
      t("configuration.workflow.seuils_invalides", { valeurs: invalides.join(", ") }),
    ]
  } else if (seuils.length === 0) {
    errors.alert_thresholds = [t("configuration.workflow.seuil_requis")]
  }
  if (Object.keys(errors).length > 0) return { errors }
  return {
    errors,
    values: {
      require_review_step: draft.require_review_step,
      warn_without_proof_submission: draft.warn_without_proof_submission,
      unjustified_alert_days: jours,
      unusual_expense_factor: facteur!,
      alert_thresholds: [...new Set(seuils)].sort((a, b) => a - b),
      default_overrun_policy: draft.default_overrun_policy,
    },
  }
}

function WorkflowForm({
  workflow,
  onSaved,
}: {
  workflow: WorkflowConfiguration
  onSaved: (workflow: WorkflowConfiguration) => void
}) {
  const { t } = useTranslation()
  const [draft, setDraft] = useState<WorkflowDraft>({
    require_review_step: workflow.require_review_step,
    warn_without_proof_submission: workflow.warn_without_proof_submission,
    unjustified_alert_days: String(workflow.unjustified_alert_days),
    unusual_expense_factor: workflow.unusual_expense_factor,
    alert_thresholds: workflow.alert_thresholds.join(", "),
    default_overrun_policy: workflow.default_overrun_policy,
  })
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)

  const set = <K extends keyof WorkflowDraft>(key: K, value: WorkflowDraft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }))
    setSaved(false)
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    const { values, errors } = validateWorkflow(t, draft)
    setFieldErrors(errors)
    setError(null)
    if (!values) {
      setError(t("configuration.workflow.corriger"))
      return
    }
    setSaving(true)
    try {
      const result = await updateWorkflowConfiguration(values)
      onSaved(result)
      setSaved(true)
    } catch (e) {
      if (e instanceof ApiError) setFieldErrors(e.fields)
      setError(e instanceof Error ? e.message : t("erreurs.enregistrement_impossible"))
    } finally {
      setSaving(false)
    }
  }

  const champ = (key: keyof WorkflowDraft) => fieldErrors[key]?.join(" ")

  return (
    <Card className="border-border/60 shadow-sm">
      <CardHeader>
        <CardTitle className="text-sm font-semibold">
          {t("configuration.workflow.titre")}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form className="grid gap-4 sm:grid-cols-2" onSubmit={handleSubmit} noValidate>
          <FormError className="sm:col-span-2">{error}</FormError>
          {saved && (
            <Alert className="sm:col-span-2">
              <CheckCircle2 className="h-4 w-4" />
              <AlertTitle>{t("configuration.workflow.enregistree_titre")}</AlertTitle>
              <AlertDescription>
                {t("configuration.workflow.enregistree_texte")}
              </AlertDescription>
            </Alert>
          )}
          <div className="flex items-center justify-between gap-3 rounded-lg border border-border/60 p-3 sm:col-span-2">
            <div>
              <Label htmlFor="require_review_step" className="block text-sm font-medium">
                {t("configuration.workflow.controle_obligatoire")}
              </Label>
              <p className="text-xs text-muted-foreground">
                {t("configuration.workflow.controle_obligatoire_aide")}
              </p>
            </div>
            <Switch
              id="require_review_step"
              checked={draft.require_review_step}
              onCheckedChange={(checked) => set("require_review_step", checked)}
            />
          </div>
          <div className="flex items-center justify-between gap-3 rounded-lg border border-border/60 p-3 sm:col-span-2">
            <div>
              <Label htmlFor="warn_without_proof_submission" className="block text-sm font-medium">
                {t("configuration.workflow.avertir_sans_piece")}
              </Label>
              <p className="text-xs text-muted-foreground">
                {t("configuration.workflow.avertir_sans_piece_aide")}
              </p>
            </div>
            <Switch
              id="warn_without_proof_submission"
              checked={draft.warn_without_proof_submission}
              onCheckedChange={(checked) => set("warn_without_proof_submission", checked)}
            />
          </div>
          <Champ
            id="unjustified_alert_days"
            label={t("configuration.workflow.delai_alerte")}
            erreur={champ("unjustified_alert_days")}
          >
            <Input
              id="unjustified_alert_days"
              inputMode="numeric"
              value={draft.unjustified_alert_days}
              onChange={(e) => set("unjustified_alert_days", e.target.value)}
              aria-invalid={Boolean(champ("unjustified_alert_days"))}
            />
          </Champ>
          <Champ
            id="unusual_expense_factor"
            label={t("configuration.workflow.facteur_inhabituel")}
            erreur={champ("unusual_expense_factor")}
          >
            <Input
              id="unusual_expense_factor"
              inputMode="decimal"
              value={draft.unusual_expense_factor}
              onChange={(e) => set("unusual_expense_factor", e.target.value)}
              aria-invalid={Boolean(champ("unusual_expense_factor"))}
            />
          </Champ>
          <Champ
            id="alert_thresholds"
            label={t("configuration.workflow.seuils")}
            erreur={champ("alert_thresholds")}
          >
            <Input
              id="alert_thresholds"
              value={draft.alert_thresholds}
              onChange={(e) => set("alert_thresholds", e.target.value)}
              placeholder="50, 80, 100"
              aria-invalid={Boolean(champ("alert_thresholds"))}
            />
          </Champ>
          <Champ
            id="default_overrun_policy"
            label={t("configuration.workflow.politique_defaut")}
            erreur={champ("default_overrun_policy")}
          >
            <NativeSelect
              id="default_overrun_policy"
              value={draft.default_overrun_policy}
              onChange={(e) => set("default_overrun_policy", e.target.value as OverrunPolicy)}
            >
              {OVERRUN_POLICIES.map((policy) => (
                <option key={policy} value={policy}>
                  {overrunPolicyLabel(t, policy)}
                </option>
              ))}
            </NativeSelect>
          </Champ>
          <div className="sm:col-span-2">
            <Button type="submit" disabled={saving}>
              {saving ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Save className="mr-2 h-4 w-4" aria-hidden />
              )}
              {saving
                ? t("configuration.workflow.enregistrement")
                : t("configuration.workflow.enregistrer")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}

function Champ({
  id,
  label,
  erreur,
  children,
}: {
  id: string
  label: string
  erreur?: string
  children: React.ReactNode
}) {
  return (
    <div className="grid gap-2">
      <Label htmlFor={id}>{label}</Label>
      {children}
      {erreur && (
        <p role="alert" className="text-xs text-destructive">
          {erreur}
        </p>
      )}
    </div>
  )
}

function PermissionsSection() {
  const { t } = useTranslation()
  const query = useQuery("permissions", () => fetchPermissionMatrix())
  const matrix = query.data

  if (query.loading && !matrix) return <Chargement />
  if (query.error && !matrix) return <Erreur message={query.error} />
  if (!matrix) return null

  return (
    <div className="space-y-4">
      <Alert>
        <Lock className="h-4 w-4" />
        <AlertTitle>{t("configuration.permissions.non_modifiables")}</AlertTitle>
        <AlertDescription>{matrix.note}</AlertDescription>
      </Alert>

      <Card className="border-border/60 shadow-sm">
        <CardContent className="pt-6">
          <div className="overflow-x-auto rounded-lg border border-border/60">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col" className="sticky left-0 z-10 min-w-[16rem] bg-card">
                    {t("configuration.permissions.droit")}
                  </TableHead>
                  {matrix.roles.map((role) => (
                    <TableHead scope="col" key={role.value} className="text-center">
                      <span className="block">{role.label}</span>
                      <span className="text-[10px] font-normal text-muted-foreground">
                        {role.siege
                          ? t("configuration.permissions.siege")
                          : t("configuration.permissions.pays")}
                      </span>
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {matrix.capabilities.map((capability) => (
                  <TableRow key={capability.key}>
                    <TableCell className="sticky left-0 z-10 bg-card">
                      <p className="font-medium">{capability.label}</p>
                      <p className="text-xs text-muted-foreground">
                        {capability.description}
                      </p>
                    </TableCell>
                    {matrix.roles.map((role) => (
                      <TableCell key={role.value} className="text-center">
                        {capability.roles.includes(role.value) ? (
                          <Badge className={STATUS_TONES.SUCCES}>{t("commun.oui")}</Badge>
                        ) : (
                          <span className="text-muted-foreground/40" aria-label={t("commun.non")}>
                            {t("commun.aucun")}
                          </span>
                        )}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

function Bloc({ titre, children }: { titre: string; children: React.ReactNode }) {
  return (
    <Card className="border-border/60 shadow-sm">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-semibold">{titre}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2.5">{children}</CardContent>
    </Card>
  )
}

function Ligne({
  label,
  valeur,
  alerte,
}: {
  label: string
  valeur: string
  alerte?: boolean
}) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-border/40 pb-2 last:border-0 last:pb-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span
        className={
          alerte ? "text-sm font-medium text-destructive" : "text-sm font-medium"
        }
      >
        {valeur}
      </span>
    </div>
  )
}

function Chargement() {
  const { t } = useTranslation()
  return (
    <div className="flex h-40 items-center justify-center" aria-busy="true">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      <span className="sr-only">{t("commun.chargement")}</span>
    </div>
  )
}

function Erreur({ message }: { message: string }) {
  const { t } = useTranslation()
  return (
    <Alert variant="destructive">
      <AlertTriangle className="h-4 w-4" />
      <AlertTitle>{t("commun.erreur")}</AlertTitle>
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  )
}
