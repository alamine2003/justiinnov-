---
name: frontend-react
description: Façon de travailler dans le frontend React de JUSTI INNOV (i18n obligatoire, composants partagés de DESIGN.md, chargement des données, droits venus du serveur, tests vitest, captures). À charger avant toute modification sous frontend/src, y compris un libellé.
---

# Frontend React

## Instructions

### Étape 1 : lire les règles

`CLAUDE.md`, puis `DESIGN.md` en entier (le skill `design-system` le
rappelle), puis `frontend/src/i18n/index.ts` et `frontend/src/lib/labels.ts`.

### Étape 2 : coder à la manière du projet

- Sans point-virgule, guillemets doubles, français dans le code et les
  commentaires.
- **Aucune chaîne visible en dur** : `const { t } = useTranslation()` dans
  un composant, `i18next.t(...)` ailleurs ; clés ajoutées dans
  `src/i18n/fr.json` **et** `en.json` (un test de parité et un test
  anti-chaînes accentuées échouent sinon). Les libellés venus du serveur
  (`*_display`) s'affichent tels quels, il les traduit déjà.
- Données : `useQuery(clé, fetcher)` pour un écran, `useReferentiel` pour
  pays, équipes, projets, managers ; remise à la page 1 dans le gestionnaire
  de filtre, jamais dans un effet ; `useDebounced` sur une recherche.
- Droits : `const { can } = useAuth()` et les clés `permissions` du serveur,
  celles de la matrice `accounts/permissions.py` (`expenses.create`,
  `expenses.review`, `expenses.validate`, `budgets.create`, `data.export`,
  `dossiers.reopen`, `configuration.manage`, `audit.read`,
  `referentiel.update`…), réglables par les administrateurs. Sur un dossier
  ou une ligne, `allowed_actions` dit ce qui se saisit encore (`edit`,
  `add_line`, `upload`, `delete`) et quelles transitions sont ouvertes.
  Jamais de test sur le code du rôle ni sur le statut pour masquer un bouton.
- Chiffres : l'interface formate (`formatAmount`, `formatRate`,
  `formatDateIn`), elle ne calcule jamais.
- Composants partagés obligatoires : `PageHeader`, `FormError`, `StatCard`,
  `EmptyRow`, `SkeletonRows`, `TruncatedNotice`, `Pagination`, badges de
  `status-badge.tsx` ; couleurs par jetons uniquement.
- Accessibilité : `aria-label` sur les boutons à icône, `role="alert"` sur
  les erreurs, liens plutôt que lignes cliquables, `DropdownMenuRadioGroup`
  pour un choix exclusif.

### Étape 3 : vérifier

```bash
cd frontend && npx tsc -b && npm run lint && npm run test && npm run build
```

Tout doit être vert, sans avertissement. Un écran modifié se regarde :
lancez la pile livrable et les captures (skill `verifier`).

### Étape 4 : consigner

Un composant partagé ou une règle d'interface nouvelle s'écrit dans
`DESIGN.md`, pas dans le composant qui l'a inspirée.
