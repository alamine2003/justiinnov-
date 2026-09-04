import { Component, type ErrorInfo, type ReactNode } from "react"
import { AlertTriangle } from "lucide-react"
import i18next from "i18next"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"

interface State {
  error: Error | null
}

/**
 * Dernier filet : une exception dans une page ne doit pas laisser un écran
 * blanc sans explication. L'utilisateur voit ce qui s'est passé et peut
 * recharger.
 */
export class ErrorBoundary extends Component<{ children: ReactNode }, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Erreur d'affichage", error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="mx-auto max-w-2xl p-6">
          <Alert variant="destructive">
            <AlertTriangle className="h-4 w-4" />
            <AlertTitle>{i18next.t("erreurs.affichage_echoue")}</AlertTitle>
            <AlertDescription>
              <p>{this.state.error.message || i18next.t("erreurs.inattendue")}</p>
              <p>
                <a href={window.location.pathname}>{i18next.t("erreurs.recharger")}</a>
              </p>
            </AlertDescription>
          </Alert>
        </div>
      )
    }
    return this.props.children
  }
}
