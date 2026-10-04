import { ArrowLeft } from "lucide-react"
import { useTranslation } from "react-i18next"
import { useLocation, useNavigate } from "react-router-dom"
import { Button } from "@/components/ui/button"
import { parentPath } from "@/lib/navigation"
import { cn } from "@/lib/utils"

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
  // Une section du menu (`/registre`, `/audit`…) n'a pour parent que
  // l'accueil : dès `lg`, la barre latérale y mène déjà, et la ligne du
  // bouton se rend au contenu (DESIGN.md, « Hauteur »).
  const section = parentPath(pathname) === "/"

  const goBack = () => {
    const state = window.history.state as { idx?: number } | null
    if ((state?.idx ?? 0) > 0) navigate(-1)
    else navigate(parentPath(pathname))
  }

  return (
    <div className={cn("mb-4 flex court:mb-2", section && "lg:hidden")}>
      <Button variant="ghost" size="sm" className="-ml-2 text-muted-foreground" onClick={goBack}>
        <ArrowLeft className="mr-2 h-4 w-4" aria-hidden />
        {t("nav.retour")}
      </Button>
    </div>
  )
}
