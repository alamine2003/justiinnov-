import { useCallback, useEffect, useState } from "react"
import { useSearchParams } from "react-router-dom"
import { AlertTriangle, Info, Loader2, Lock } from "lucide-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { PageHeader } from "@/components/ui/page-header"
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
import { RatesSection } from "@/pages/configuration/rates-section"
import { UsersSection } from "@/pages/configuration/users-section"
import { fetchConfiguration, fetchPermissionMatrix } from "@/lib/accounts"
import { BRAND } from "@/lib/brand"
import type { Configuration, PermissionMatrix } from "@/lib/types"

const ONGLETS = [
  { value: "general", label: "Général" },
  { value: "utilisateurs", label: "Utilisateurs" },
  { value: "pays", label: "Pays" },
  { value: "permissions", label: "Permissions" },
] as const

export function ConfigurationPage() {
  // L'onglet vit dans l'URL : un lien vers « Configuration › Permissions »
  // doit rouvrir cet onglet, pas le premier.
  const [params, setParams] = useSearchParams()
  const onglet = params.get("onglet") ?? "general"

  return (
    <div className="space-y-6">
      <PageHeader
        title="Configuration"
        description="Paramètres de la plateforme, comptes, pays et droits. Réservé aux administrateurs du siège."
      />

      <Tabs
        value={onglet}
        onValueChange={(value) => setParams({ onglet: value })}
      >
        <TabsList className="flex w-full flex-wrap justify-start bg-muted/60">
          {ONGLETS.map((item) => (
            <TabsTrigger key={item.value} value={item.value}>
              {item.label}
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
      </Tabs>
    </div>
  )
}

function GeneralSection() {
  const [config, setConfig] = useState<Configuration | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setConfig(await fetchConfiguration())
    } catch (e) {
      setError(e instanceof Error ? e.message : "Chargement impossible")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  if (loading) return <Chargement />
  if (error) return <Erreur message={error} />
  if (!config) return null

  return (
    <div className="space-y-4">
      <Alert>
        <Info className="h-4 w-4" />
        <AlertTitle>Paramètres fixés au démarrage</AlertTitle>
        <AlertDescription>
          Ils viennent de l'environnement du serveur. Les afficher ici permet de
          vérifier ce qui tourne réellement, plutôt que ce que le fichier de
          configuration laisse supposer. Les modifier suppose un redémarrage.
        </AlertDescription>
      </Alert>

      <div className="grid gap-4 lg:grid-cols-2">
        <Bloc titre="Application">
          <Ligne label="Nom" valeur={BRAND.name} />
          <Ligne label="Version" valeur={BRAND.version} />
          <Ligne label="Développement" valeur={BRAND.developer} />
          <Ligne label="Fuseau du serveur" valeur={config.systeme.fuseau} />
          <Ligne
            label="Mode debug"
            valeur={config.systeme.mode_debug ? "Activé" : "Désactivé"}
            alerte={config.systeme.mode_debug}
          />
        </Bloc>

        <Bloc titre="Alertes">
          <Ligne
            label="Seuils de consommation"
            valeur={config.alertes.seuils.map((s) => `${s} %`).join(" · ")}
          />
          <Ligne
            label="Dépense inhabituelle"
            valeur={`au-delà de ${config.alertes.facteur_depense_inhabituelle} × la moyenne du pays`}
          />
        </Bloc>

        <Bloc titre="Justificatifs">
          <Ligne label="Stockage" valeur={config.justificatifs.stockage} />
          <Ligne
            label="Taille maximale"
            valeur={`${config.justificatifs.taille_max_mo} Mo`}
          />
          <Ligne
            label="Formats acceptés"
            valeur={config.justificatifs.formats_acceptes.join(" ")}
          />
        </Bloc>

        <Bloc titre="Budget et notifications">
          <Ligne
            label="Devise de consolidation"
            valeur={config.budget.devise_de_consolidation}
          />
          <Ligne
            label="Envoi d'e-mails"
            valeur={
              config.notifications.email_configure
                ? "Serveur SMTP configuré"
                : "Aucun serveur — les messages partent dans les logs"
            }
            alerte={!config.notifications.email_configure}
          />
          <Ligne label="Expéditeur" valeur={config.notifications.expediteur} />
        </Bloc>
      </div>

      <RatesSection />
    </div>
  )
}

function PermissionsSection() {
  const [matrix, setMatrix] = useState<PermissionMatrix | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setMatrix(await fetchPermissionMatrix())
    } catch (e) {
      setError(e instanceof Error ? e.message : "Chargement impossible")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  if (loading) return <Chargement />
  if (error) return <Erreur message={error} />
  if (!matrix) return null

  return (
    <div className="space-y-4">
      <Alert>
        <Lock className="h-4 w-4" />
        <AlertTitle>Droits non modifiables</AlertTitle>
        <AlertDescription>{matrix.note}</AlertDescription>
      </Alert>

      <Card className="border-border/60 shadow-sm">
        <CardContent className="pt-6">
          <div className="overflow-x-auto rounded-lg border border-border/60">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="sticky left-0 z-10 min-w-[16rem] bg-card">
                    Droit
                  </TableHead>
                  {matrix.roles.map((role) => (
                    <TableHead key={role.value} className="text-center">
                      <span className="block">{role.label}</span>
                      <span className="text-[10px] font-normal text-muted-foreground">
                        {role.siege ? "siège" : "pays"}
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
                          <Badge className="bg-emerald-500 hover:bg-emerald-500">
                            oui
                          </Badge>
                        ) : (
                          <span className="text-muted-foreground/40">—</span>
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
  return (
    <div className="flex h-40 items-center justify-center">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
    </div>
  )
}

function Erreur({ message }: { message: string }) {
  return (
    <Alert variant="destructive">
      <AlertTriangle className="h-4 w-4" />
      <AlertTitle>Erreur</AlertTitle>
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  )
}
