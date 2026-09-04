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
- Droits : n'ajoutez jamais un test de rôle dans une vue ; déclarez
  `write_roles`, `read_roles`, `action_write_roles` avec les ensembles de
  `accounts/permissions.py`. Un nouveau droit = un ensemble nommé, une
  capacité dans `CAPABILITIES`, un test de refus.
- Cloisonnement : `CountryScopedMixin` (`country_lookup`, `country_via`,
  `team_lookup`) et, pour les clés étrangères de la charge utile,
  `ChampCloisonne` ou `PerimetreMixin`.
- Écritures sensibles : `transaction.atomic()` + `select_for_update()` ;
  trace via `expenses.audit.record` ou `ChangeLog` avec avant/après ;
  adresse via `core.requetes.client_ip`.
- Chiffres : `Decimal`, `Coalesce`, agrégations en SQL (`with_consumption`,
  `with_totals`), jamais de boucle Python qui additionne des lignes.
- Chaînes visibles : `gettext_lazy as _` (modèles, choix, workflow) ou
  `gettext as _` (vues, serializers), puis ajoutez l'entrée anglaise dans
  `<app>/locale/en/LC_MESSAGES/django.po`.
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
docker compose run --rm --entrypoint sh backend -c 'for d in */locale; do (cd "$(dirname "$d")" && django-admin compilemessages -l en >/dev/null); done'
docker compose run --rm -e POSTGRES_DB=justi_dev_x --entrypoint python backend manage.py test <app> --noinput
docker compose run --rm -e POSTGRES_DB=justi_dev_x --entrypoint python backend manage.py makemigrations --check --dry-run
```

Fixtures : `accounts.tests.test_scoping.make_user(username, role,
countries, teams=(), totp_confirmed=True)` et `expenses.tests.base.ExpenseTestCase`
(`make_expense`, `submit_dossier`). Un correctif sans le test qui l'aurait
attrapé n'est pas fini.

### Étape 5 : consigner

Une décision de conception nouvelle va dans `docs/model-de-donnees.md` §8 ;
une règle nouvelle dans `CLAUDE.md` ; un contrat d'API nouveau dans
`README.md` et dans `frontend/src/lib/types.ts` côté client.
