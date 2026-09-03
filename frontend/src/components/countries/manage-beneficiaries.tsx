import { useCallback, useEffect, useState } from "react"
import { Badge } from "@/components/ui/badge"
import { ManageRows } from "@/components/countries/manage-rows"
import {
  createBeneficiary,
  fetchBeneficiaries,
  updateBeneficiary,
} from "@/lib/expenses"
import { BENEFICIARY_KINDS, type Beneficiary } from "@/lib/types"

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
  const [rows, setRows] = useState<Beneficiary[]>([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const page = await fetchBeneficiaries({
        country: countryId,
        page_size: 200,
      })
      setRows(page.results)
    } finally {
      setLoading(false)
    }
  }, [countryId])

  useEffect(() => {
    void load()
  }, [load])

  const save = async (data: Record<string, unknown>, itemId?: number) => {
    const payload = { country: countryId, ...data }
    if (itemId) await updateBeneficiary(itemId, payload)
    else await createBeneficiary(payload)
    await load()
  }

  return (
    <ManageRows
      title="Prospects et bénéficiaires"
      description="Qui reçoit l'argent, ou qui la dépense vise. La liste est propre au pays."
      rows={rows}
      loading={loading}
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
              <Badge className="bg-emerald-500 hover:bg-emerald-500">Actif</Badge>
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
  )
}
