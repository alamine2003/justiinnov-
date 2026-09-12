import { ArrowLeft } from "lucide-react"
import { useTranslation } from "react-i18next"
import { useLocation, useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { parentPath } from "@/lib/navigation"

/**
 * Bouton « Retour », en haut de chaque page sauf l'accueil.
 *
 * Il revient à l'écran précédent quand la navigation a commencé dans
 * l'application — le routeur numérote ses entrées (`history.state.idx`) —
 * et, sinon (page ouverte directement, lien reçu, favori), à la liste de
 * la section : un retour qui sortirait de l'application n'en est pas un.
 */
export function BackButton() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { pathname } = useLocation()

  if (pathname === "/") return null

  const goBack = () => {
    const state = window.history.state as { idx?: number } | null
    if ((state?.idx ?? 0) > 0) navigate(-1)
    else navigate(parentPath(pathname))
  }

  return (
    <div className="mb-4 flex">
      <Button variant="ghost" size="sm" className="-ml-2 text-muted-foreground" onClick={goBack}>
        <ArrowLeft className="mr-2 h-4 w-4" aria-hidden />
        {t("nav.retour")}
      </Button>
    </div>
  )
}
