---
name: database
description: Conventions du modèle de données et des migrations Django de JUSTI INNOV (PostgreSQL 16) — clés PROTECT, contraintes en base, index utiles, migrations de reprise, base privée pour tester, retour arrière. À charger avant de toucher un models.py ou un dossier migrations/.
---

# Base de données

## Instructions

### Étape 1 : lire ce qui existe

`docs/model-de-donnees.md` est la référence du schéma et des décisions
(§8, numérotées). Les modèles : `core` (pays, équipes, projets, intitulés,
catégories, `ChangeLog`, `WorkflowConfiguration`), `accounts`
(`UserProfile`, périmètres, TOTP), `budget` (`Budget`, `BudgetReallocation`,
`ExchangeRate`), `expenses` (`Dossier`, `Expense`, `Proof`, `Beneficiary`,
`AuditLog`), `notifications`. Ordre des apps : `core < accounts <
notifications < budget < expenses < reporting` — un modèle ne référence
jamais une app de rang supérieur.

### Étape 2 : règles du modèle

- `on_delete=PROTECT` partout : rien ne se supprime, une entité se
  désactive (`is_active`).
- Ce que la base doit refuser est une `CheckConstraint` ou une
  `UniqueConstraint`, pas seulement une validation de sérialiseur :
  `depense_montant_positif`, `depense_justifie_borne`,
  `depense_declaree_imputee`, `unique_dossier_par_pays`,
  `piece_unique_par_dossier` (partielle, `replaces IS NULL`),
  `unique_notification_par_evenement`, `core_workflowconfiguration_unique`
  (singleton `id = 1`).
- Une course se tranche en base (contrainte) ou sous verrou
  (`select_for_update`, dans les services de transition), jamais par une
  lecture puis une écriture.
- Index pour les filtres réels des vues (`country`, `status`, `date`,
  journaux par `(country, created_at)` et `(object_type, object_id)`), pas
  pour le principe. `Meta.ordering` finit par `-pk` (tri stable).
- Montants en `DecimalField(16, 2)`, taux en `(10, 4)` ; dates de dépense en
  `DateTimeField` lues dans le fuseau du pays (`Country.timezone`).
- Les journaux `ChangeLog` et `AuditLog` sont immuables : déclencheurs SQL
  (`core/migrations/0009`, `expenses/migrations/0008`) ; on n'y écrit que par
  `core.journal.tracer`.

### Étape 3 : migrations

```bash
docker compose run --rm -e POSTGRES_DB=justi_db --entrypoint python backend manage.py makemigrations <app> -n <nom_en_francais>
docker compose run --rm -e POSTGRES_DB=justi_db --entrypoint python backend manage.py makemigrations --check --dry-run
docker compose run --rm -e POSTGRES_DB=justi_db --entrypoint python backend manage.py migrate
docker compose run --rm -e POSTGRES_DB=justi_db --entrypoint python backend manage.py migrate <app> <numero_precedent>   # retour arrière
```

- Une contrainte ajoutée sur une table peuplée s'accompagne d'une
  `RunPython` de reprise, et de `SET CONSTRAINTS ALL IMMEDIATE` avant
  l'`AddConstraint` (modèle : `expenses/migrations/0007`).
- Une migration doit être réversible ; une `RunPython` porte son
  `reverse_code` (ou `noop` assumé et commenté).
- Aucune migration destructive (suppression de colonne, de table, de
  données) sans le « GO » explicite du propriétaire.
- Les données d'amorçage : `seed_users` (comptes, depuis un fichier ignoré
  par git), `seed_demo --base-jetable` (jeu de démonstration, pile jetable
  seulement).

### Étape 4 : vérifier

Suite de l'app puis suite complète sur base privée (`-e POSTGRES_DB=justi_db`),
jamais deux suites sur la même base. Mesurer une requête suspecte :
`CaptureQueriesContext` (recette dans le skill `scalabilite`), ou
`EXPLAIN ANALYZE` par `docker compose exec db psql -U "$POSTGRES_USER"`.

### Terminé quand

Modèle et contraintes conformes à `PLAN.md`, migration nommée en français
et réversible, `makemigrations --check` propre, suite verte, schéma décrit
dans `docs/model-de-donnees.md` (décision en §8 s'il y a lieu).
