import { AlertTriangle, Loader2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"

export function Chargement() {
  const { t } = useTranslation()
  return (
    <div className="flex h-40 items-center justify-center" aria-busy="true">
      <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      <span className="sr-only">{t("commun.chargement")}</span>
    </div>
  )
}

export function Erreur({ message }: { message: string }) {
  const { t } = useTranslation()
  return (
    <Alert variant="destructive">
      <AlertTriangle className="h-4 w-4" />
      <AlertTitle>{t("commun.erreur")}</AlertTitle>
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  )
}
