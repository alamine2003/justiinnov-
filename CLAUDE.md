# Plateforme de contrôle budgétaire

Suivi des dépenses de pays africains et de leurs justificatifs. Le but n'est
pas d'autoriser des dépenses, mais de savoir **ce qui a été dépensé, quand, où,
au profit de qui — et où est la preuve**.

## Avant de toucher à l'interface

**Lisez [`DESIGN.md`](DESIGN.md)** à la racine. Il fait référence : palette,
typographie, composants partagés, états, accessibilité, boucle de vérification.
N'inventez pas de style, ne recopiez pas une couleur en dur, ne refaites pas un
composant qui existe.

## Démarrer

```bash
docker compose up -d          # db, minio, backend, frontend
# Frontend http://localhost:5173 · API http://localhost:8000/api/
```

Aucun compte n'est créé automatiquement et **aucun mot de passe ne figure dans
le dépôt**. Les comptes viennent de `backend/seed_users.local.json` (ignoré par
git) via `manage.py seed_users`.

## Vérifier

```bash
docker compose run --rm --entrypoint python backend manage.py test
cd frontend && npx tsc -b && npm run lint && npm run test
```

Pour l'interface, lancez aussi les scripts de capture décrits dans `DESIGN.md` :
ils échouent sur toute erreur de console, et plusieurs défauts n'ont été
trouvés qu'en regardant les images.

La CI (`.github/workflows/ci.yml`) rejoue tout cela, captures comprises, sur
la pile livrable (`docker-compose.ci.yml`). La livraison (`cd.yml`) publie
les images et déploie `deploy/` ; voir `deploy/README.md`.

## Règles que le code doit respecter

Elles ne sont pas des préférences : les enfreindre casse la raison d'être de
l'application.

- **Le périmètre est l'Afrique.** Un pays se crée depuis la liste des codes
  ISO d'Afrique (`backend/core/africa.py`) ; tout autre code est refusé.
  Étendre le périmètre demande de modifier ce fichier, donc une décision
  explicite.
- **Une dépense soumise est irréversible.** Elle ne revient pas au brouillon,
  ne se modifie plus, ne se supprime pas. Seul un brouillon — jamais soumis,
  donc sans valeur probante — peut être retiré par son auteur.
- **Une dépense non justifiée pèse quand même sur l'enveloppe.** L'absence de
  preuve ne fait pas revenir l'argent ; elle se lit dans l'écart entre dépensé
  et justifié.
- **Rien ne se supprime**, hors brouillon. Le retrait d'une entité de
  référentiel se fait par désactivation (`is_active`) ; l'API répond 405 sur
  `DELETE`.
- **Les chiffres se calculent côté serveur.** Solde, écart, taux : l'interface
  affiche, elle ne recalcule pas.
- **Le cloisonnement par pays est vérifié sur le queryset**, pas seulement à
  l'affichage. Un objet hors périmètre répond 404, sans révéler son existence.
  Les écritures sont revalidées : une charge utile ne doit pas permettre de
  créer une entité chez le voisin.
- **Toute action sensible laisse une trace** dans `ChangeLog` ou `AuditLog` :
  qui, quoi, quand, depuis quelle adresse, ancienne et nouvelle valeur.
- **Le pays déclare, le siège constate.** Un responsable pays ne justifie
  jamais une dépense, pas même la sienne : il la soumet, et le siège tranche.
  Et celui qui a saisi une dépense ne peut pas la justifier lui-même, fût-il
  au siège — il faut deux personnes.
- **Déclarer tient en une action.** Le pays remplit ses lignes, joint la
  pièce et soumet le dossier : ses lignes partent avec lui. Un dossier vide ne
  se soumet pas ; un dossier sans pièce se soumet avec un avertissement.
- **Un rejet exige un motif.**
- **Une requête `GET` n'écrit rien.** Les alertes sont calculées à la
  lecture ; leur notification passe par `manage.py notify_alerts`, pour ne
  pas dépendre de quelqu'un qui ouvre une page.

## Repères

| Sujet | Où |
|---|---|
| Modèle de données figé | `docs/model-de-donnees.md` |
| Circuit de justification | `backend/expenses/workflow.py` |
| Rôles et périmètres | `backend/accounts/` |
| Calculs budgétaires | `backend/budget/aggregates.py` |
| Interface | `DESIGN.md` |

## Conventions

- Le code, les commentaires et les messages de commit sont **en français**,
  comme l'interface.
- Frontend sans point-virgule en fin de ligne, guillemets doubles.
- Un correctif s'accompagne du test qui l'aurait attrapé.
