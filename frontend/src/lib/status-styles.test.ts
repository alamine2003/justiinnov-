import { describe, expect, it } from "vitest"
import { AUDIT_ACTIONS, HISTORY_ACTIONS } from "./labels"
import { ACTION_STYLE } from "./status-styles"

/**
 * Régression : une action sans teinte retombait sur `bg-secondary`, dont le
 * texte disparaissait sur fond clair — les connexions de l'onglet
 * « Référentiel et comptes » de l'audit ne se lisaient plus.
 */
describe("ACTION_STYLE", () => {
  it("teinte chaque action du journal d'audit et de l'historique", () => {
    const sansTeinte = [...AUDIT_ACTIONS, ...HISTORY_ACTIONS].filter((action) => !ACTION_STYLE[action])
    expect(sansTeinte).toEqual([])
  })
})
