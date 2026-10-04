import { useTranslation } from "react-i18next"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { NativeSelect } from "@/components/ui/native-select"
import { fetchCountries } from "@/lib/countries"
import { REFERENTIEL_PAGE_SIZE, useReferentiel } from "@/lib/referentiel"

/** Période et pays, en tête de chaque onglet. */
export function BarreDePeriode({
  lire,
  changer,
}: {
  lire: (cle: string) => string
  changer: (valeurs: Record<string, string>) => void
}) {
  const { t } = useTranslation()
  const pays = useReferentiel("countries", () =>
    fetchCountries({ page_size: REFERENTIEL_PAGE_SIZE, is_active: true }),
  )
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="grid gap-1">
        <Label htmlFor="audit-debut" className="text-xs">{t("audit.filtres.debut")}</Label>
        <Input
          id="audit-debut"
          type="date"
          value={lire("debut")}
          onChange={(e) => changer({ debut: e.target.value, page: "" })}
          className="w-40"
        />
      </div>
      <div className="grid gap-1">
        <Label htmlFor="audit-fin" className="text-xs">{t("audit.filtres.fin")}</Label>
        <Input
          id="audit-fin"
          type="date"
          value={lire("fin")}
          onChange={(e) => changer({ fin: e.target.value, page: "" })}
          className="w-40"
        />
      </div>
      <div className="grid gap-1">
        <Label htmlFor="audit-pays" className="text-xs">{t("commun.pays")}</Label>
        <NativeSelect
          id="audit-pays"
          value={lire("country")}
          onChange={(e) => changer({ country: e.target.value, page: "" })}
          className="w-48"
        >
          <option value="">{t("dossiers.liste.tous_pays")}</option>
          {(pays.data?.results ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </NativeSelect>
      </div>
    </div>
  )
}
