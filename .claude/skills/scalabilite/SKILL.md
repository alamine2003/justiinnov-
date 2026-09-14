---
name: scalabilite
description: Budgets de performance et recettes de mesure de JUSTI INNOV — requêtes par route, charge à 30 utilisateurs, limites de gunicorn, nginx, DRF et PostgreSQL, exports en mémoire, cache. À charger pour une revue de performance, une simulation ou avant d'ajouter une liste, un agrégat ou un export.
---

# Scalabilité

## Ce qui est mesuré (référence, septembre 2026, 1 163 dossiers / 3 465 lignes)

| Mesure | Valeur | Budget |
|---|---|---|
| Requêtes SQL par route de liste | 9 à 18, indépendant de la taille de page | ≤ 20 et constant |
| 30 utilisateurs, réflexion 1 s, deux pays | 70 req/s, p95 < 250 ms, CPU backend ~70 % | p95 < 500 ms |
| 30 utilisateurs sans pause (stress) | ~100 req utiles/s, p95 600–900 ms, CPU 200 % | goulot : gunicorn |
| Export CSV d'un exercice | 400 Ko, 285 ms | < 2 s |

Le goulot est le CPU de gunicorn (2 workers × 4 threads par défaut), pas
PostgreSQL (10 connexions, 0 attente de verrou). `GUNICORN_WORKERS` se règle
dans `.env` sans reconstruire.

## Instructions

### Compter les requêtes d'une route

```python
# docker compose exec -T backend python manage.py shell -c "exec(open('/tmp/mesure.py').read())"
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient
client = APIClient(); client.credentials(HTTP_AUTHORIZATION="Token …")
with CaptureQueriesContext(connection) as ctx:
    rep = client.get("/api/dossiers/?page_size=20")
print(len(ctx), [q["sql"][:70] for q in ctx.captured_queries if float(q["time"]) > 0.05])
```

Un compte qui grandit avec `page_size` est un N+1 : `select_related` /
`prefetch_related` dans `get_queryset`, ou annotation (`with_totals`,
`with_consumption`), jamais une boucle Python. Un test `assertNumQueries` ou
une comparaison à une et trois lignes (voir `budget/tests/test_budgets.py`,
`test_la_liste_ne_relit_pas_la_matrice_par_ligne`) fixe le gain.

### Charger

`python3 simulation/charge.py http://127.0.0.1:8000 90 1.0` (direct
gunicorn) puis `http://127.0.0.1:8080` (derrière Caddy et nginx). Sondes
CPU/mémoire et connexions PostgreSQL incluses. Pièges : `UserRateThrottle`
2 000/h par compte (jeton partagé = blocage une heure ; `cache.clear()` sur
la pile jetable), connexion 10/min par adresse.

### Règles

- Pagination partout, `page_size` plafonné à 200.
- Agrégats en SQL (`Sum`, `Coalesce`, `Subquery`), lecture de la
  configuration une fois par requête (`_configuration(self)` dans les
  sérialiseurs, `matrice_effective` mémorisée).
- Exports en mémoire : acceptable jusqu'à quelques dizaines de milliers de
  lignes ; au-delà, découper par mois ou diffuser en flux (`StreamingHttpResponse`).
- Fichiers en flux (`FileResponse`), empreinte SHA-256 par blocs.
- Cache : `DatabaseCache` partagé entre workers (limites de débit,
  configuration) ; `LocMemCache` sous test.
- Pas de tâche asynchrone : les alertes se notifient par `notify_alerts`
  (scheduler APScheduler), pas à la lecture.

### Rapport d'une revue

Risque → mesure → charge de rupture → correctif proposé (diff court + test),
classé CRITIQUE / ÉLEVÉ / MOYEN / FAIBLE. Rien n'est appliqué sans le Chef.
