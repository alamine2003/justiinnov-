/**
 * Types TypeScript du contrat d'API, tirés du schéma OpenAPI du backend.
 *
 *   npx tsx scripts/generer-types.mts            # depuis docs/api/schema.json
 *   npx tsx scripts/generer-types.mts --schema   # régénère d'abord le schéma
 *
 * Le schéma (`docs/api/schema.json`) est versionné : la CI vérifie qu'une
 * génération fraîche du backend lui est identique, puis que ce script rend
 * `src/lib/types.generated.ts` à l'identique. Sans `--schema`, le script ne
 * demande donc rien à Docker ; avec, il appelle `manage.py spectacular` sur
 * une base privée et réécrit le schéma avant les types.
 *
 * `src/lib/types.generated.ts` ne se modifie pas à la main : `types.ts` y
 * prend ses alias et n'ajoute que les types composés.
 *
 * openapi-typescript 7 déclare TypeScript ^5 en dépendance de pair ; le
 * projet est en 6 et le générateur n'emploie que l'API stable du compilateur
 * (fabrique d'AST, impression). `package.json` aligne donc cette dépendance
 * de pair sur la version du projet (`overrides`).
 */
import { execFileSync } from "node:child_process"
import { readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import openapiTS, { astToString } from "openapi-typescript"

const racine = join(import.meta.dirname, "..", "..")
const schema = join(racine, "docs", "api", "schema.json")
const sortie = join(racine, "frontend", "src", "lib", "types.generated.ts")

if (process.argv.includes("--schema")) {
  // Même commande que la CI, sur une base privée : deux suites de tests
  // lancées sur la même base se détruisent, la génération n'y touche pas.
  const json = execFileSync(
    "docker",
    [
      "compose", "run", "--rm", "-T",
      "-e", "POSTGRES_DB=justi_schema",
      "-e", "EMAIL_BACKEND_CONSOLE=1",
      "--entrypoint", "python", "backend",
      "manage.py", "spectacular", "--format", "openapi-json", "--validate", "--fail-on-warn",
    ],
    { cwd: racine, encoding: "utf8", stdio: ["ignore", "pipe", "inherit"], maxBuffer: 64 * 1024 * 1024 },
  )
  writeFileSync(schema, json)
  console.log(`Schéma régénéré : ${schema}`)
}

const document = JSON.parse(readFileSync(schema, "utf8"))
const ast = await openapiTS(document, {
  // Les champs `readOnly` sont marqués `readonly` : l'interface ne les
  // réécrit pas, le serveur les calcule.
  immutable: false,
  // `additionalProperties` absent : un objet est ce que le schéma dit, pas
  // un dictionnaire ouvert.
  additionalProperties: false,
  alphabetize: false,
  defaultNonNullable: true,
  // `minItems`/`maxItems` donnent des tuples : `[ancienne, nouvelle]` d'un
  // `diff` reste un couple, pas un tableau de longueur inconnue.
  arrayLength: true,
  // Les énumérations restent des unions de chaînes : l'interface compare
  // des valeurs, elle ne manipule pas d'objets `enum`.
  enum: false,
})

const entete = [
  "// Généré par scripts/generer-types.mts depuis docs/api/schema.json.",
  "// Ne pas modifier à la main : `npm run types:api` régénère ce fichier,",
  "// et la CI refuse une version qui ne correspondrait plus au schéma.",
  "",
].join("\n")

// Même convention que le reste du frontend : pas de point-virgule final. Les
// espaces insécables des descriptions françaises (« … », « : ») deviennent
// des espaces ordinaires : le lint les signale comme irréguliers.
const contenu = astToString(ast)
  .replace(/;$/gm, "")
  .replace(/[\u00A0\u202F]/g, " ")
writeFileSync(sortie, entete + contenu)
console.log(`Types écrits : ${sortie}`)
