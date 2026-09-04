/**
 * Clés de traduction typées : `t("clé.inconnue")` est une erreur de
 * compilation, `t("clé", { defaultValue })` reste permis pour les clés
 * construites à partir d'une valeur serveur.
 */
import "i18next"
import type fr from "./fr.json"

declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "translation"
    resources: { translation: typeof fr }
  }
}
