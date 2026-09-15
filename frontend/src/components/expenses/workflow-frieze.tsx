import { Check, X } from "lucide-react"
import { useTranslation } from "react-i18next"
import { CIRCUIT, circuitStep, workflowLabel } from "@/lib/labels"
import type { WorkflowStatus } from "@/lib/types"
import { cn } from "@/lib/utils"

/**
 * Le circuit d'un dossier en frise horizontale : ce qui est fait, où l'on
 * en est, ce qui reste. La frise ne dit que l'état — elle ne propose aucune
 * action : celles-ci viennent d'`allowed_actions`, dans l'en-tête de page.
 *
 * Elle n'affiche ni date ni auteur par étape : ces informations vivent dans
 * le journal d'audit, réservé aux administrateurs, et un DF qui lit cet
 * écran n'y a pas accès.
 */
export function FriseDuCircuit({ status }: { status: WorkflowStatus }) {
  const { t } = useTranslation()
  const courante = circuitStep(status)
  const constatManque = status === "unjustified"

  return (
    <ol className="flex items-start" aria-label={t("dossiers.circuit.titre")}>
      {CIRCUIT.map((etape, index) => {
        const faite = index < courante
        const ici = index === courante
        // Le constat de non-justification occupe la place de « justifié » :
        // c'est bien cette etape-la qui porte alors le libelle du refus.
        const libelle = workflowLabel(t, ici && constatManque ? status : etape)
        return (
          <li
            key={etape}
            className={cn("flex min-w-0 items-start", index > 0 && "flex-1")}
            aria-current={ici ? "step" : undefined}
          >
            {index > 0 && (
              <span
                aria-hidden
                className={cn("mt-[13px] h-0.5 flex-1", faite || ici ? "bg-marque-fort" : "bg-border")}
              />
            )}
            <span className="flex w-28 shrink-0 flex-col items-center gap-2 px-1">
              <Pastille faite={faite} ici={ici} manque={constatManque} />
              <span
                className={cn(
                  "text-center text-xs leading-tight",
                  faite || ici ? "font-medium" : "text-muted-foreground",
                  ici && constatManque && "text-destructive",
                )}
              >
                {libelle}
              </span>
            </span>
          </li>
        )
      })}
    </ol>
  )
}

function Pastille({
  faite,
  ici,
  manque,
}: {
  faite: boolean
  ici: boolean
  manque: boolean
}) {
  if (faite) {
    return (
      <span
        aria-hidden
        className="flex h-[26px] w-[26px] items-center justify-center rounded-full bg-marque-fort text-marque-fort-foreground"
      >
        <Check className="h-3.5 w-3.5" />
      </span>
    )
  }
  if (ici && manque) {
    return (
      <span
        aria-hidden
        className="flex h-[26px] w-[26px] items-center justify-center rounded-full bg-destructive text-destructive-foreground"
      >
        <X className="h-3.5 w-3.5" />
      </span>
    )
  }
  if (ici) {
    return (
      <span
        aria-hidden
        className="flex h-[26px] w-[26px] items-center justify-center rounded-full border-[2.5px] border-statut-attente bg-card"
      >
        <span className="h-2 w-2 rounded-full bg-statut-attente" />
      </span>
    )
  }
  return (
    <span
      aria-hidden
      className="h-[26px] w-[26px] rounded-full border-2 border-dashed border-border bg-card"
    />
  )
}
