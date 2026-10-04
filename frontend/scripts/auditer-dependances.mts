/**
 * `npm audit` au seuil `high`, hors avis tolérés — la porte « Dépendances
 * vulnérables » de la CI, côté frontend.
 *
 *   node scripts/auditer-dependances.mts
 *
 * `npm audit` n'a pas d'équivalent au `--ignore-vuln <id>` de `pip-audit` :
 * un avis sans correctif publié bloquerait toutes les livraisons sans rien
 * pouvoir y faire. Ce script lit `npm audit --json`, écarte les avis de
 * `AVIS_TOLERES` — chacun avec son pourquoi — et échoue sur tout autre avis
 * `high` ou `critical`. Il échoue aussi quand un avis toléré n'est plus
 * signalé : une exception ne survit pas à son motif (décision 112).
 *
 * Il ne dépend de rien : le job d'audit ne fait pas `npm ci`, et Node lit ce
 * fichier tel quel (syntaxe effaçable, `erasableSyntaxOnly`).
 */
import { spawnSync } from "node:child_process"

/** Identifiant GHSA → pourquoi l'avis ne bloque pas. À retirer dès que le correctif est publié. */
export const AVIS_TOLERES: ReadonlyMap<string, string> = new Map([
  [
    "GHSA-vfj7-8cjw-p6xm",
    "braces <= 3.0.3, sans correctif publié (octobre 2026). Atteint par la CLI shadcn " +
      "(fast-glob → micromatch → braces), outil de développement dont les motifs " +
      "sont écrits par le développeur ; absent de l'image livrée (nginx + dist/).",
  ],
])

const GRAVITES_BLOQUANTES = new Set(["high", "critical"])

export type Avis = { id: string, paquet: string, gravite: string, titre: string, url: string }

type Via = string | { name?: string, title?: string, url?: string, severity?: string }
export type RapportNpm = { vulnerabilities?: Record<string, { via?: Via[] }>, error?: unknown }

/**
 * Les avis bloquants d'un rapport `npm audit --json` (format 2).
 *
 * Seuls les objets de `via` sont des avis ; une chaîne n'y fait que relayer
 * celui d'une dépendance, déjà compté sous elle.
 */
export function avisBloquants(
  rapport: RapportNpm,
  toleres: ReadonlyMap<string, string> = AVIS_TOLERES,
): { bloquants: Avis[], toleresVus: string[] } {
  const vus = new Map<string, Avis>()
  for (const [paquet, vulnerabilite] of Object.entries(rapport.vulnerabilities ?? {})) {
    for (const via of vulnerabilite.via ?? []) {
      if (typeof via === "string") continue
      const url = via.url ?? ""
      const id = url.split("/").pop() || `${via.name ?? paquet}:${via.title ?? ""}`
      if (!vus.has(id)) {
        vus.set(id, {
          id, url, paquet: via.name ?? paquet, gravite: via.severity ?? "", titre: via.title ?? "",
        })
      }
    }
  }
  const avis = [...vus.values()]
  return {
    bloquants: avis.filter((a) => GRAVITES_BLOQUANTES.has(a.gravite) && !toleres.has(a.id)),
    toleresVus: avis.filter((a) => toleres.has(a.id)).map((a) => a.id),
  }
}

function principal(): number {
  const audit = spawnSync("npm", ["audit", "--json"], { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 })
  let rapport: RapportNpm
  try {
    rapport = JSON.parse(audit.stdout) as RapportNpm
  } catch {
    console.error("npm audit n'a pas rendu de JSON lisible :", audit.stderr || audit.stdout)
    return 1
  }
  if (rapport.error) {
    console.error("npm audit a échoué :", JSON.stringify(rapport.error))
    return 1
  }

  const { bloquants, toleresVus } = avisBloquants(rapport)
  let code = 0
  for (const a of bloquants) {
    console.error(`[${a.gravite}] ${a.paquet} — ${a.titre} — ${a.url}`)
    code = 1
  }
  for (const id of AVIS_TOLERES.keys()) {
    if (toleresVus.includes(id)) {
      console.log(`Toléré : ${id} — ${AVIS_TOLERES.get(id)}`)
    } else {
      console.error(`${id} n'est plus signalé : retirez-le de AVIS_TOLERES (scripts/auditer-dependances.mts).`)
      code = 1
    }
  }
  if (code === 0) console.log("Aucun avis high ou critical hors avis tolérés.")
  return code
}

if (import.meta.main) process.exit(principal())
