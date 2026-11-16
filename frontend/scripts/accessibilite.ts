/**
 * Contrôle d'accessibilité des scripts de capture (décision 129).
 *
 * Chaque écran capturé passe aussi par axe-core, sur les règles WCAG 2.2
 * niveaux A et AA. Une violation grave ou critique (`serious`, `critical`)
 * fait échouer le script, comme une erreur de console : contraste
 * insuffisant, champ sans nom, nom accessible qui ne reprend pas le texte
 * affiché, liste mal formée… Les violations modérées ou mineures sont
 * seulement consignées.
 *
 * axe ne voit que ce qui est à l'écran au moment du contrôle : il complète
 * le regard sur les images, il ne le remplace pas (DESIGN.md).
 */
import { AxeBuilder } from "@axe-core/playwright"
import type { Page } from "playwright"

const REGLES_WCAG = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
const BLOQUANTES = new Set(["serious", "critical"])

/** Rend la liste des violations bloquantes de l'écran, déjà mises en forme. */
export async function controlerAccessibilite(page: Page, ecran: string): Promise<string[]> {
  const { violations } = await new AxeBuilder({ page }).withTags(REGLES_WCAG).analyze()
  const bloquantes: string[] = []
  for (const violation of violations) {
    const cibles = violation.nodes.map((noeud) => noeud.target.join(" ")).slice(0, 3)
    const message = `${ecran} — ${violation.id} (${violation.impact}, ${violation.nodes.length} élément(s)) : ${violation.help} — ${cibles.join(" | ")}`
    if (BLOQUANTES.has(violation.impact ?? "")) {
      console.log(`  ✗ accessibilité : ${message}`)
      bloquantes.push(`accessibilité : ${message}`)
    } else {
      console.log(`  · accessibilité (non bloquant) : ${message}`)
    }
  }
  return bloquantes
}
