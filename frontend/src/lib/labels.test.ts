import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"
import { notificationKindIcon } from "./labels"

/** Les natures de notification, telles que le contrat d'API les déclare. */
const schema = JSON.parse(readFileSync(resolve(__dirname, "../../../docs/api/schema.json"), "utf8"))
const NATURES: string[] = schema.components.schemas.NotificationKindEnum.enum

describe("notificationKindIcon", () => {
  it("donne une icône à chaque nature que le serveur émet, corbeille comprise", () => {
    expect(NATURES).toContain("trashed")
    for (const nature of NATURES) {
      expect(notificationKindIcon(nature), nature).toBeDefined()
    }
  })
})
