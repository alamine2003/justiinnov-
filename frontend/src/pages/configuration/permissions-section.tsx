import { useState, type FormEvent, Fragment } from "react"
import { CheckCircle2, Info, Loader2, Lock, Save, RotateCcw } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Legende } from "@/components/ui/charts"
import { FormError } from "@/components/ui/form-error"
import { Switch } from "@/components/ui/switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { useAuth } from "@/context/use-auth"
import { fetchPermissionMatrix, updatePermissionMatrix } from "@/lib/accounts"
import { ApiError, type FieldErrors } from "@/lib/api"
import { STATUS_TONES } from "@/lib/status-styles"
import type { PermissionMatrix } from "@/lib/types"
import { useQuery } from "@/lib/use-query"
import { cn } from "@/lib/utils"
import { Chargement, Erreur } from "@/pages/configuration/section-states"

export function PermissionsSection() {
  const query = useQuery("permissions", () => fetchPermissionMatrix())
  // Chaque enregistrement remonte une matrice neuve : la clé remonte le
  // formulaire, dont l'état local repart de ce que le serveur a retenu. La
  // confirmation, elle, survit au remontage : elle vit ici.
  const [version, setVersion] = useState(0)
  const [matrix, setMatrix] = useState<PermissionMatrix | null>(null)
  const [enregistre, setEnregistre] = useState(false)
  const courante = matrix ?? query.data ?? null

  if (query.loading && !courante) return <Chargement />
  if (query.error && !courante) return <Erreur message={query.error} />
  if (!courante) return null

  return (
    <MatriceDesDroits
      key={version}
      matrix={courante}
      enregistre={enregistre}
      onModification={() => setEnregistre(false)}
      onSaved={(suivante) => {
        setMatrix(suivante)
        setEnregistre(true)
        setVersion((v) => v + 1)
      }}
    />
  )
}

export function MatriceDesDroits({
  matrix,
  enregistre = false,
  onModification,
  onSaved,
}: {
  matrix: PermissionMatrix
  /** Le dernier enregistrement a réussi et rien n'a bougé depuis. */
  enregistre?: boolean
  onModification?: () => void
  onSaved: (matrix: PermissionMatrix) => void
}) {
  const { t } = useTranslation()
  const { me, refreshProfile } = useAuth()
  const [choix, setChoix] = useState<Record<string, string[]>>(() =>
    Object.fromEntries(matrix.capabilities.map((c) => [c.key, c.roles])),
  )
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({})

  const memes = (a: string[], b: string[]) =>
    a.length === b.length && [...a].sort().every((v, k) => v === [...b].sort()[k])
  const modifiees = matrix.capabilities.filter((c) => !memes(choix[c.key], c.roles))
  const groupes = [...new Set(matrix.capabilities.map((c) => c.group))]

  const basculer = (cle: string, role: string, accorde: boolean) => {
    onModification?.()
    setChoix((etat) => ({
      ...etat,
      [cle]: accorde ? [...etat[cle], role] : etat[cle].filter((r) => r !== role),
    }))
  }

  const enregistrer = async (e: FormEvent) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setFieldErrors({})
    try {
      const suivante = await updatePermissionMatrix(
        Object.fromEntries(modifiees.map((c) => [c.key, choix[c.key]])),
      )
      // Les droits du compte courant ont pu changer : `can` doit le savoir.
      // Le serveur a enregistré : une relecture qui échoue ne doit pas le
      // faire passer pour un refus.
      await refreshProfile().catch(() => undefined)
      onSaved(suivante)
    } catch (err) {
      if (err instanceof ApiError) {
        setFieldErrors(err.fields)
        setError(err.message)
      } else {
        setError(t("configuration.permissions.erreur"))
      }
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={(e) => void enregistrer(e)} className="space-y-4">
      <Alert>
        <Info className="h-4 w-4" />
        <AlertTitle>{t("configuration.permissions.titre")}</AlertTitle>
        <AlertDescription>
          {t("configuration.permissions.description")} {matrix.note}
        </AlertDescription>
      </Alert>

      <Card className="border-border/60 shadow-sm">
        <CardContent className="space-y-4 pt-6">
          <div className="overflow-x-auto rounded-lg border border-border/60">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col" className="sticky left-0 z-10 min-w-[16rem] bg-card">
                    {t("configuration.permissions.droit")}
                  </TableHead>
                  {/* Cinq colonnes doivent tenir côte à côte : le libellé du
                      rôle s'enroule sur deux lignes plutôt que d'élargir. */}
                  {matrix.roles.map((role) => (
                    <TableHead scope="col" key={role.value} className="text-center align-bottom">
                      <span className="mx-auto block max-w-[9rem] whitespace-normal text-xs leading-tight">
                        {role.label}
                      </span>
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
                {groupes.map((groupe) => (
                  <Fragment key={groupe}>
                    <TableRow className="bg-muted/40 hover:bg-muted/40">
                      <TableCell
                        colSpan={matrix.roles.length + 1}
                        className="sticky left-0 text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                      >
                        {groupe}
                      </TableCell>
                    </TableRow>
                    {matrix.capabilities
                      .filter((c) => c.group === groupe)
                      .map((capability) => {
                        const modifiee = !memes(choix[capability.key], capability.roles)
                        const horsDefaut = !memes(choix[capability.key], capability.default_roles)
                        return (
                          <TableRow key={capability.key}>
                            {/* Une ligne modifiée porte un filet à son
                                entrée : la pastille « Modifié » seule se
                                perdait au milieu de cinquante lignes. La
                                colonne est figée au défilement horizontal,
                                donc son fond reste opaque — un aplat teinté
                                y laisserait voir les colonnes qui passent
                                dessous. */}
                            <TableCell
                              className={cn(
                                "sticky left-0 z-10 border-l-[3px] bg-card align-top",
                                modifiee ? "border-l-marque" : "border-l-transparent",
                              )}
                            >
                              <div className="flex items-start justify-between gap-2">
                                <div>
                                  <p className="font-medium">{capability.label}</p>
                                  <p className="text-xs text-muted-foreground">
                                    {capability.description}
                                  </p>
                                  {fieldErrors[capability.key] && (
                                    <p className="mt-1 text-xs text-destructive" role="alert">
                                      {fieldErrors[capability.key].join(" ")}
                                    </p>
                                  )}
                                </div>
                                <div className="flex shrink-0 flex-col items-end gap-1">
                                  {modifiee && (
                                    <Badge className={STATUS_TONES.ATTENTE}>
                                      {t("configuration.permissions.modifie")}
                                    </Badge>
                                  )}
                                  {horsDefaut && (
                                    <Button
                                      type="button"
                                      variant="ghost"
                                      size="sm"
                                      className="h-7 px-2 text-xs"
                                      aria-label={t("configuration.permissions.retablir_aria", {
                                        droit: capability.label,
                                      })}
                                      onClick={() => {
                                        onModification?.()
                                        setChoix((etat) => ({
                                          ...etat,
                                          [capability.key]: capability.default_roles,
                                        }))
                                      }}
                                    >
                                      <RotateCcw className="mr-1 h-3 w-3" aria-hidden />
                                      {t("configuration.permissions.retablir")}
                                    </Button>
                                  )}
                                </div>
                              </div>
                            </TableCell>
                            {matrix.roles.map((role) => {
                              const toujours = capability.fixed_roles.includes(role.value)
                              const jamais = capability.locked_roles.includes(role.value)
                              // Le serveur dit qui règle chaque ligne (`settable_by_roles`) :
                              // une case hors de portée se voit, ne se change pas.
                              const reglable = me?.role != null && capability.settable_by_roles.includes(me.role)
                              const accorde = choix[capability.key].includes(role.value)
                              const aria = t("configuration.permissions.case_aria", {
                                droit: capability.label,
                                role: role.label,
                              })
                              return (
                                // Une case verrouillée se voit : son fond
                                // grisé dit « ici, rien à régler » avant même
                                // qu'on lise l'icône.
                                <TableCell
                                  key={role.value}
                                  className={cn(
                                    "text-center align-top",
                                    (toujours || jamais) && "bg-muted/50",
                                  )}
                                >
                                  {toujours || jamais ? (
                                    <span
                                      className="inline-flex items-center justify-center text-muted-foreground/60"
                                      title={t(
                                        toujours
                                          ? "configuration.permissions.toujours"
                                          : "configuration.permissions.jamais",
                                      )}
                                    >
                                      {toujours ? (
                                        <CheckCircle2 className="h-4 w-4" aria-hidden />
                                      ) : (
                                        <Lock className="h-4 w-4" aria-hidden />
                                      )}
                                      <span className="sr-only">
                                        {aria}
                                        {" — "}
                                        {t(
                                          toujours
                                            ? "configuration.permissions.toujours"
                                            : "configuration.permissions.jamais",
                                        )}
                                      </span>
                                    </span>
                                  ) : (
                                    <Switch
                                      size="sm"
                                      checked={accorde}
                                      disabled={!reglable}
                                      title={reglable ? undefined : t("configuration.permissions.hors_de_votre_role")}
                                      aria-label={aria}
                                      onCheckedChange={(valeur) =>
                                        basculer(capability.key, role.value, valeur)
                                      }
                                    />
                                  )}
                                </TableCell>
                              )
                            })}
                          </TableRow>
                        )
                      })}
                  </Fragment>
                ))}
              </TableBody>
            </Table>
          </div>

          {error && <FormError>{error}</FormError>}
          {enregistre && modifiees.length === 0 && (
            <Alert>
              <CheckCircle2 className="h-4 w-4" />
              <AlertDescription>{t("configuration.permissions.enregistre")}</AlertDescription>
            </Alert>
          )}

          {/* Ce qui reste à enregistrer se lit en pied de matrice, avec la
              légende des cases : c'est là que le regard revient après avoir
              parcouru les cinq colonnes. */}
          <div
            className={cn(
              "-mx-6 -mb-6 flex flex-wrap items-center justify-between gap-3 border-t px-6 py-4",
              modifiees.length > 0 ? "border-marque/30 bg-marque/5" : "border-border/60",
            )}
          >
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
              <p
                className={cn(
                  "text-sm font-medium",
                  modifiees.length > 0 ? "text-marque-fort" : "text-muted-foreground",
                )}
                aria-live="polite"
              >
                {modifiees.length > 0
                  ? t("configuration.permissions.modifications", { count: modifiees.length })
                  : t("configuration.permissions.aucune_modification")}
              </p>
              <Legende
                items={[
                  { tone: "bg-primary", label: t("configuration.permissions.legende_accorde") },
                  {
                    tone: "bg-muted-foreground/50",
                    label: t("configuration.permissions.toujours"),
                  },
                  {
                    tone: "border border-border bg-muted",
                    label: t("configuration.permissions.jamais"),
                  },
                ]}
              />
            </div>
            <div className="flex gap-2">
              {modifiees.length > 0 && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    onModification?.()
                    setChoix(Object.fromEntries(matrix.capabilities.map((c) => [c.key, c.roles])))
                  }}
                >
                  {t("configuration.permissions.annuler")}
                </Button>
              )}
              <Button type="submit" disabled={saving || modifiees.length === 0}>
                {saving ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />
                ) : (
                  <Save className="mr-2 h-4 w-4" aria-hidden />
                )}
                {t("commun.enregistrer")}
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </form>
  )
}
