---
name: backend-django
description: Façon de travailler dans le backend Django de JUSTI INNOV (modèles, serializers, vues, workflow, migrations, traductions, tests sur base privée). À charger avant toute modification sous backend/, y compris un simple correctif.
---

# Backend Django

## Instructions

### Étape 1 : lire les règles et le contexte

`CLAUDE.md` (règles), `docs/model-de-donnees.md` (modèle, décisions
numérotées), puis le module visé et ses tests. Les apps : `core`
(référentiel, historique), `accounts` (rôles, périmètres, 2FA), `budget`
(enveloppes, réallocations, taux), `expenses` (dossiers, dépenses, pièces,
workflow), `notifications`, `reporting` (tableau de bord, alertes, exports,
import).

### Étape 2 : coder à la manière du projet

- Français partout : code, docstrings, messages, noms de tests. Un
  commentaire explique **pourquoi**, jamais quoi.
- Droits : n'ajoutez jamais un test de rôle dans une vue ni un service ;
  déclarez `write_capability`, `read_capability`,
  `action_write_capabilities`, `action_read_capabilities` avec une clé de
  `CAPACITES` (`accounts/permissions.py`), et `exiger_la_capacite(cle,
  acteur)` ou `roles_pour(cle)` dans un service. Un nouveau droit = une
  `Capacite` (clé `ressource.verbe`, groupe, défaut, verrous), un test de
  refus, une traduction. Les rôles effectifs viennent de la configuration
  (`WorkflowConfiguration.capability_roles`, décision 43) : un ensemble de
  rôles figé dans le code est un défaut.
- Cloisonnement : une seule primitive, `accounts.perimetre.filtrer`
  (pays, équipes du manager) appelée par `CountryScopedMixin`
  (`country_lookup`, `country_via`, `team_lookup`), et `ChampCloisonne`
  (`accounts/perimetre.py`) pour les clés étrangères de la charge utile.
  Le test `accounts/tests/test_traversee.py` parcourt toutes les routes.
- Écritures sensibles : `transaction.atomic()` + `select_for_update()` ;
  trace via la façade unique `core.journal.tracer(request, action,
  instance, famille=…, avant=…, apres=…)` qui route vers `ChangeLog` ou
  `AuditLog` et remplit auteur, IP et user-agent ; aucune écriture directe
  dans un journal (un test structurel le refuse).
- Dépendances entre apps : ordre strict `core < accounts < notifications <
  budget < expenses < reporting`, vérifié par `core/tests/test_dependances.py` ;
  les statuts du circuit vivent dans `core/statuts.py`, l'authentification et
  le référentiel dans `accounts`.
- Chiffres : `Decimal`, `Coalesce`, agrégations en SQL (`with_consumption`,
  `with_totals`), jamais de boucle Python qui additionne des lignes.
- Chaînes visibles : `gettext_lazy as _` (modèles, choix, workflow) ou
  `gettext as _` (vues, serializers), puis l'entrée anglaise dans le
  **catalogue unique** `backend/locale/en/LC_MESSAGES/django.po`
  (décision 42). Depuis `backend/`, `docker compose run --rm --entrypoint
  python backend manage.py makemessages -l en --ignore=tests --no-obsolete
  --no-wrap` y ramène les chaînes nouvelles avec un `msgstr` vide, à
  traduire à la main ; aucun `msgstr` vide ni `fuzzy` ne reste, la CI le
  refuse (`msgfmt --check`, `msgattrib --untranslated`).
- Modèle : `PROTECT` sur les clés étrangères, `CheckConstraint` pour ce que
  la base doit refuser, index pour les filtres réels, `-pk` en fin de tri.

### Étape 3 : migrations

```bash
docker compose run --rm -e POSTGRES_DB=justi_dev_x --entrypoint python backend manage.py makemigrations <app> -n <nom_en_francais>
```

Une contrainte ajoutée sur une table déjà peuplée s'accompagne d'une
`RunPython` de reprise (voir `expenses/migrations/0007`) et, sous
PostgreSQL, de `SET CONSTRAINTS ALL IMMEDIATE` avant l'`AddConstraint`.

### Étape 4 : tester sur une base privée

Deux suites lancées en parallèle sur la même base se détruisent. Donnez à
chaque terminal ou agent un nom de base distinct :

```bash
docker compose run --rm --entrypoint django-admin backend compilemessages -l en -v0 --ignore=.venv
docker compose run --rm -e POSTGRES_DB=justi_dev_x -e EMAIL_BACKEND_CONSOLE=1 --entrypoint python backend manage.py test <app> --noinput
docker compose run --rm -e POSTGRES_DB=justi_dev_x -e EMAIL_BACKEND_CONSOLE=1 --entrypoint python backend manage.py test --noinput --parallel auto
docker compose run --rm -e POSTGRES_DB=justi_dev_x --entrypoint python backend manage.py makemigrations --check --dry-run
```

La suite complète tourne en une quinzaine de secondes en série, moins de
dix en parallèle : lancez-la entière, pas seulement votre app. Les tests
utilisent un cache mémoire et un hachage rapide des mots de passe (bloc
« Réglages de test » de settings.py, actif sous `manage.py test`) ; les
fixtures de décor vivent dans `setUpTestData`, ce que chaque test mute
reste dans `setUp`.

Fixtures : `accounts.tests.test_scoping.make_user(username, role,
countries, teams=(), totp_confirmed=True)` et `expenses.tests.base.ExpenseTestCase`
(`make_expense`, `submit_dossier`). Un correctif sans le test qui l'aurait
attrapé n'est pas fini.

### Étape 5 : régénérer le contrat d'API

Après toute modification d'une vue ou d'un sérialiseur :

```bash
cd frontend && npm run types:api -- --schema
```

Cela régénère `docs/api/schema.json` (drf-spectacular, sans avertissement
toléré) puis `frontend/src/lib/types.generated.ts` ; la CI compare les deux.
Un `SerializerMethodField` nouveau porte `@extend_schema_field`, une action
composée à la main porte `@extend_schema`, un champ facultatif en réponse
s'ajoute à `CHAMPS_FACULTATIFS_EN_REPONSE` dans `config/schema.py`.

### Étape 6 : consigner

Une décision de conception nouvelle va dans `docs/model-de-donnees.md` §8 ;
une règle nouvelle dans `CLAUDE.md` ; un contrat d'API nouveau dans
`README.md` et dans `frontend/src/lib/types.ts` côté client.
