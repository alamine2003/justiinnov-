import { WifiOff } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { useOnline } from "@/lib/online"

/**
 * Bandeau hors ligne.
 *
 * L'application installée s'ouvre sans réseau grâce au cache de l'interface,
 * mais aucune donnée métier n'est mise en cache : sans serveur, il n'y a
 * rien à faire, et il faut le dire plutôt que d'accumuler des erreurs.
 */
export function OfflineNotice() {
  const { t } = useTranslation()
  const online = useOnline()
  if (online) return null
  return (
    <div aria-live="polite" className="sticky top-0 z-50 px-4 pt-4 sm:px-6">
      <Alert variant="destructive" className="mx-auto max-w-7xl bg-card shadow-sm">
        <WifiOff className="h-4 w-4" />
        <AlertTitle>{t("layout.hors_ligne_titre")}</AlertTitle>
        <AlertDescription>{t("layout.hors_ligne_texte")}</AlertDescription>
      </Alert>
    </div>
  )
}
