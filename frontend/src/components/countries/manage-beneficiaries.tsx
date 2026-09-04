import { Badge } from "@/components/ui/badge"
import { FormError } from "@/components/ui/form-error"
import { TruncatedNotice } from "@/components/ui/truncated-notice"
import { ManageRows } from "@/components/countries/manage-rows"
import {
  createBeneficiary,
  fetchBeneficiaries,
  updateBeneficiary,
} from "@/lib/expenses"
import { REFERENTIEL_PAGE_SIZE, invalidateReferentiel } from "@/lib/referentiel"
import { STATUS_TONES } from "@/lib/status-styles"
import { BENEFICIARY_KINDS, type Beneficiary } from "@/lib/types"
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
  const query = useQuery(
    `beneficiaries:manage:${countryId}`,
    (signal) =>
      fetchBeneficiaries({ country: countryId, page_size: REFERENTIEL_PAGE_SIZE }, signal),
    { fallback: "Bénéficiaires indisponibles" },
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
      <TruncatedNotice page={query.data} noun="bénéficiaires" />
      <ManageRows<Beneficiary>
        title="Prospects et bénéficiaires"
        description="Qui reçoit l'argent, ou qui la dépense vise. La liste est propre au pays."
        rows={query.data?.results ?? []}
        loading={query.loading}
        emptyMessage="Aucun bénéficiaire. Ajoutez-en pour pouvoir les rattacher aux dépenses."
        columns={[
          { key: "name", header: "Nom" },
          {
            key: "kind",
            header: "Type",
            render: (b) => <Badge variant="secondary">{b.kind_display}</Badge>,
          },
          { key: "contact", header: "Contact" },
          {
            key: "is_active",
            header: "Statut",
            render: (b) =>
              b.is_active ? (
                <Badge className={STATUS_TONES.SUCCES}>Actif</Badge>
              ) : (
                <Badge variant="secondary">Inactif</Badge>
              ),
          },
        ]}
        detectActive={(b) => b.is_active}
        defaultForm={{ name: "", kind: "beneficiary", contact: "" }}
        formFields={[
          { key: "name", label: "Nom", placeholder: "Station Lomé" },
          {
            key: "kind",
            label: "Type",
            options: BENEFICIARY_KINDS,
          },
          {
            key: "contact",
            label: "Contact",
            placeholder: "Téléphone ou e-mail",
            optional: true,
          },
        ]}
        canManage={canManage}
        onSave={save}
      />
    </div>
  )
}
