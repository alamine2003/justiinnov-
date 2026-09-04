---
name: revue-code
description: Liste de contrôle de revue de code propre à JUSTI INNOV (règles métier de CLAUDE.md, cloisonnement, traçabilité, tests, i18n, interface). À utiliser avant tout commit, à la demande d'une relecture, ou par l'agent relecteur ; complète le skill code-review générique et la revue CodeRabbit sur GitHub.
---

# Revue de code JUSTI INNOV

La revue ne juge pas le style : elle cherche ce qui casserait la raison
d'être de l'application. Lisez `CLAUDE.md` d'abord ; chaque règle ci-dessous
en découle.

## Instructions

### Étape 1 : délimiter

`git status` puis `git diff` (ou `git diff main...` pour une branche). Lisez
tout le diff, puis le contexte de chaque modification. Notez les fichiers
touchés par app : un changement dans `expenses` sans test dans
`expenses/tests/` est suspect d'emblée.

### Étape 2 : passer la liste de contrôle

**Règles métier**
- Le manager déclare, le DM contrôle, le DF constate : aucune route ne
  permet à un rôle de pays de justifier, ni au DM de trancher.
- Une dépense soumise ne se modifie ni ne se supprime ; la seule
  réouverture est celle des administrateurs, motivée et tracée.
- Une dépense non justifiée pèse sur l'enveloppe ; l'écart se calcule côté
  serveur ; l'interface affiche, elle ne recalcule pas.
- Rien ne se supprime : `PROTECT`, désactivation, 405 sur `DELETE`.
- Un rejet et une réouverture exigent un motif.
- Un `GET` n'écrit rien, hors audit des exports et téléchargements.

**Cloisonnement et droits**
- Filtrage sur le queryset (`CountryScopedMixin`, `team_lookup`), 404 muet
  hors périmètre, clés étrangères de la charge utile restreintes au
  périmètre (`ChampCloisonne`, `PerimetreMixin`).
- Rôles : `accounts/permissions.py` est la seule source. DM et DF n'ont
  aucun droit d'administration ; enveloppes, exports, import, réouverture,
  audit et comptes sont réservés selon la matrice.
- Toute action sensible laisse une trace (`AuditLog`, `ChangeLog`) avec
  auteur, IP (`core.requetes.client_ip`), avant et après.

**Concurrence et données**
- Transaction et `select_for_update` autour des transitions, soumissions,
  réallocations, dépôts.
- `Decimal` partout, jamais `float` ; fuseau du pays pour l'exercice.
- Migration présente pour tout changement de modèle, avec reprise des
  données existantes si une contrainte s'ajoute.

**Tests**
- Chaque correctif a le test qui l'aurait attrapé ; chaque nouveau droit a
  son test de refus.
- Un test qui passe pour une mauvaise raison (assertion sur le statut HTTP
  seulement, fixture qui masque la règle) est un constat.

**Interface**
- `DESIGN.md` respecté : composants partagés, aucune couleur brute, états
  vides et erreurs (`FormError`, `role="alert"`), clavier.
- Toute chaîne visible passe par i18next, clés présentes dans `fr.json` et
  `en.json` ; côté serveur, `gettext` et catalogue `locale/en` à jour.
- Pas de point-virgule, guillemets doubles, français.

### Étape 3 : vérifier par exécution ce qui peut l'être

Sur une base privée, jamais la suite complète en parallèle d'une autre :

```bash
docker compose run --rm -e POSTGRES_DB=justi_revue --entrypoint python backend manage.py makemigrations --check --dry-run
docker compose run --rm -e POSTGRES_DB=justi_revue --entrypoint python backend manage.py test <app.tests.module> --noinput
cd frontend && npx tsc -b && npm run lint && npm run test
```

### Étape 4 : rendre le verdict

Constats par sévérité (bloquant / important / mineur), chacun avec
`fichier:ligne`, scénario, correctif et test. Puis « ce qui est bien fait »
en trois lignes, puis : prêt à commiter ou non. En français.

## Relecture automatique sur GitHub

Le dépôt peut être relu par CodeRabbit sur chaque pull request. Le serveur
MCP déclaré dans `.mcp.json` permet de lire ses remarques et de les traiter
depuis Claude Code ; voir `references/coderabbit.md`.
