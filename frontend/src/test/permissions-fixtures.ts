import type { Permissions } from "@/lib/types"

/**
 * Droits d'un manager, tels que `/api/me/` les rend par défaut : la saisie
 * et rien d'autre. Sert aux tests qui construisent un profil ; une clé
 * ajoutée à la matrice serveur apparaît ici par le type, pas par oubli.
 */
export const PERMISSIONS_DU_PAYS: Permissions = {
  "users.read": false,
  "users.create": false,
  "users.update": false,
  "configuration.manage": false,
  "audit.read": false,
  "history.read": false,
  "countries.create": false,
  "countries.update": false,
  "referentiel.create": false,
  "referentiel.update": false,
  "budgets.create": false,
  "budgets.update": false,
  "reallocations.request": false,
  "reallocations.decide": false,
  "rates.manage": false,
  "expenses.create": true,
  "expenses.update": true,
  "expenses.delete": true,
  "proofs.upload": true,
  "dossiers.submit": true,
  "expenses.review": false,
  "expenses.validate": false,
  "expenses.close": false,
  "proofs.review": false,
  "dossiers.reopen": false,
  "data.export": false,
  "data.import": false,
}
