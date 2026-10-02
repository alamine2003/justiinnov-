import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"
import { TruncatedNotice } from "@/components/ui/truncated-notice"
import { ManageRows } from "@/components/countries/manage-rows"
import { createDossierKind, fetchDossierKinds, updateDossierKind } from "@/lib/countries"
import { PROJECT_KINDS, projectKindLabel } from "@/lib/labels"
import { REFERENTIEL_PAGE_SIZE, invalidateReferentiel } from "@/lib/referentiel"
import { STATUS_TONES } from "@/lib/status-styles"
import type { DossierKind } from "@/lib/types"
import { useQuery } from "@/lib/use-query"
import { Erreur } from "@/pages/configuration/section-states"

/**
 * La liste commune des types de dossiers (décision 101).
 *
 * Commune aux dix-sept filiales et tenue par le siège : un type s'ajoute
 * ou se désactive, il ne se supprime pas — des dossiers l'emploient. Son
 * type de projet ne change plus dès qu'un dossier l'emploie ; le serveur le
 * refuse et le dialogue affiche le motif.
 */
export function DossierKindsSection() {
  const { t } = useTranslation()
  const query = useQuery(
    "configuration:types-de-dossiers",
    (signal) => fetchDossierKinds({ page_size: REFERENTIEL_PAGE_SIZE }, signal),
    { fallback: t("configuration.types_dossiers.chargement_impossible") },
  )

  const save = async (data: Record<string, unknown>, id?: number) => {
    if (id) await updateDossierKind(id, data)
    else await createDossierKind(data)
    // Les formulaires d'ouverture et d'import gardent la liste en cache.
    invalidateReferentiel((key) => key.startsWith("dossier-kinds:"))
    query.reload()
  }

  return (
    <div className="space-y-4">
      {query.error && <Erreur message={query.error} />}
      <TruncatedNotice page={query.data} noun={t("configuration.types_dossiers.noun_pluriel")} />
      <Card className="border-border/60 shadow-sm">
        <CardContent className="pt-6">
          <ManageRows<DossierKind>
            title={t("configuration.types_dossiers.titre")}
            description={t("configuration.types_dossiers.description")}
            rows={query.data?.results ?? []}
            loading={query.loading}
            columns={[
              { key: "name", header: t("champs.name") },
              { key: "project_kind_display", header: t("projets.type") },
              { key: "description", header: t("commun.description") },
              {
                key: "is_active",
                header: t("commun.statut"),
                render: (k) =>
                  k.is_active ? (
                    <Badge className={STATUS_TONES.SUCCES}>{t("commun.actif")}</Badge>
                  ) : (
                    <Badge className={STATUS_TONES.ARCHIVE}>{t("commun.desactive")}</Badge>
                  ),
              },
            ]}
            detectActive={(k) => k.is_active}
            defaultForm={{ project_kind: PROJECT_KINDS[0], name: "", description: "" }}
            formFields={[
              {
                key: "project_kind",
                label: t("projets.type"),
                options: PROJECT_KINDS.map((value) => ({ value, label: projectKindLabel(t, value) })),
              },
              {
                key: "name",
                label: t("champs.name"),
                placeholder: t("configuration.types_dossiers.nom_placeholder"),
              },
              { key: "description", label: t("commun.description"), optional: true },
            ]}
            onSave={save}
          />
        </CardContent>
      </Card>
    </div>
  )
}
