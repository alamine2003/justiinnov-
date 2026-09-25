import { useTranslation } from "react-i18next"
import { Badge } from "@/components/ui/badge"
import { FormError } from "@/components/ui/form-error"
import { TruncatedNotice } from "@/components/ui/truncated-notice"
import { ManageRows } from "@/components/countries/manage-rows"
import {
  createBeneficiary,
  fetchBeneficiaries,
  updateBeneficiary,
} from "@/lib/expenses"
import { beneficiaryKinds } from "@/lib/labels"
import { REFERENTIEL_PAGE_SIZE, invalidateReferentiel } from "@/lib/referentiel"
import { STATUS_TONES } from "@/lib/status-styles"
import type { Beneficiary } from "@/lib/types"
import { useQuery } from "@/lib/use-query"

/**
 * Prospects, clients, fournisseurs et bénéficiaires d'un pays.
 *
 * Ils étaient choisissables dans le formulaire de dépense mais ne se
 * créaient nulle part : la liste ne pouvait que rester vide. Ils vivent
 * ici, avec le reste du référentiel du pays.
 *
 * Chargés à part plutôt que dans la fiche du pays : le référentiel
 * appartient à `core`, les bénéficiaires à `expenses`, et faire connaître
 * l'un à l'autre inverserait la dépendance entre les deux applications.
 */
export function ManageBeneficiaries({
  countryId,
  canManage,
}: {
  countryId: number
  canManage: boolean
}) {
  const { t } = useTranslation()
  const query = useQuery(
    `beneficiaries:manage:${countryId}`,
    (signal) =>
      fetchBeneficiaries({ country: countryId, page_size: REFERENTIEL_PAGE_SIZE }, signal),
    { fallback: t("pays.beneficiaires.indisponibles") },
  )

  const save = async (data: Record<string, unknown>, itemId?: number) => {
    const payload = { country: countryId, ...data }
    if (itemId) await updateBeneficiary(itemId, payload)
    else await createBeneficiary(payload)
    // Le formulaire de dépense garde sa propre copie en cache.
    invalidateReferentiel(`beneficiaries:${countryId}`)
    query.reload()
  }

  return (
    <div className="space-y-3">
      <FormError>{query.error}</FormError>
      <TruncatedNotice page={query.data} noun={t("pays.beneficiaires.nom_pluriel")} />
      <ManageRows<Beneficiary>
        title={t("pays.beneficiaires.titre")}
        description={t("pays.beneficiaires.description")}
        rows={query.data?.results ?? []}
        loading={query.loading}
        emptyMessage={t("pays.beneficiaires.vide")}
        columns={[
          { key: "name", header: t("champs.name") },
          {
            key: "kind",
            header: t("champs.kind"),
            render: (b) => <Badge variant="secondary">{b.kind_display}</Badge>,
          },
          {
            key: "contact",
            header: t("pays.beneficiaires.contact"),
            // Décision 93 : téléphone ou e-mail. Un bénéficiaire saisi avant
            // elle, sans l'un ni l'autre, se signale ici — le serveur le dit
            // (`contact_manquant`), l'écran ne le déduit pas.
            render: (b) =>
              b.contact_manquant ? (
                <Badge
                  className={STATUS_TONES.ATTENTE}
                  title={t("pays.beneficiaires.a_completer_titre")}
                >
                  {t("pays.beneficiaires.a_completer")}
                </Badge>
              ) : (
                <span className="text-sm">
                  {[b.phone, b.email].filter(Boolean).join(" · ")}
                </span>
              ),
          },
          {
            key: "is_active",
            header: t("commun.statut"),
            render: (b) =>
              b.is_active ? (
                <Badge className={STATUS_TONES.SUCCES}>{t("pays.statut.actif")}</Badge>
              ) : (
                <Badge variant="secondary">{t("pays.statut.inactif")}</Badge>
              ),
          },
        ]}
        detectActive={(b) => b.is_active}
        defaultForm={{ name: "", kind: "beneficiary", phone: "", email: "", contact: "" }}
        formFields={[
          {
            key: "name",
            label: t("champs.name"),
            placeholder: t("pays.beneficiaires.nom_placeholder"),
          },
          {
            key: "kind",
            label: t("champs.kind"),
            options: beneficiaryKinds(t),
          },
          {
            key: "phone",
            label: t("pays.beneficiaires.telephone"),
            placeholder: t("pays.beneficiaires.telephone_placeholder"),
            type: "tel",
            optional: true,
            mention: t("pays.beneficiaires.l_un_des_deux"),
          },
          {
            key: "email",
            label: t("pays.beneficiaires.email"),
            placeholder: t("pays.beneficiaires.email_placeholder"),
            type: "email",
            optional: true,
            mention: t("pays.beneficiaires.l_un_des_deux"),
          },
          {
            key: "contact",
            label: t("pays.beneficiaires.autres"),
            placeholder: t("pays.beneficiaires.autres_placeholder"),
            optional: true,
          },
        ]}
        canManage={canManage}
        onSave={save}
      />
    </div>
  )
}
