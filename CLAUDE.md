# JUSTI INNOV — plateforme de contrôle budgétaire

Suivi des dépenses des filiales africaines du groupe INNOV PHARMA et de leurs
justificatifs. Le but n'est pas d'autoriser des dépenses, mais de savoir **ce
qui a été dépensé, quand, où, au profit de qui — et où est la preuve**.

L'équipe de développement compte **une seule personne** : la documentation
doit se suffire à elle-même. Ce qu'un fichier ne dit pas, personne ne le
sait ; une décision se consigne là où on la cherchera (`README.md`,
`docs/model-de-donnees.md` §8, `deploy/README.md`), dans le même commit.

## Avant de toucher à l'interface

**Lisez [`DESIGN.md`](DESIGN.md)** à la racine. Il fait référence : palette,
typographie, composants partagés, états, accessibilité, boucle de vérification.
N'inventez pas de style, ne recopiez pas une couleur en dur, ne refaites pas un
composant qui existe.

## Démarrer

```bash
docker compose up -d          # db, minio, backend, scheduler, frontend
# Frontend http://localhost:5173 · API http://localhost:8000/api/
# Les ports ne sont ouverts que sur 127.0.0.1 (base sur 5433, MinIO sur 9000/9001).
```

Aucun compte n'est créé automatiquement et **aucun mot de passe ne figure dans
le dépôt**. Les comptes viennent de `backend/seed_users.local.json` (ignoré par
git) via `manage.py seed_users`.

## Vérifier

```bash
docker compose run --rm --entrypoint python backend manage.py test
cd frontend && npx tsc -b && npm run lint && npm run test
```

Ce sont les mêmes commandes que dans `README.md` et la CI ; ne documentez
pas une variante ailleurs. **Deux suites backend ne tournent pas en parallèle
sur la même base** : Django crée `test_<POSTGRES_DB>` puis la détruit, et la
seconde suite détruirait celle de la première. Pour travailler à plusieurs,
donnez à chacune sa base avec `-e POSTGRES_DB=justi_<nom>`.

Pour l'interface, lancez aussi les scripts de capture décrits dans `DESIGN.md`
(parcours, connexion, thème sombre) : ils échouent sur toute erreur de
console, et plusieurs défauts n'ont été trouvés qu'en regardant les images.

La CI (`.github/workflows/ci.yml`) rejoue tout cela, captures comprises, sur
la pile livrable (`docker-compose.ci.yml`) ; elle tourne sur chaque PR et
au sein de la livraison (`cd.yml`), qui publie les images et déploie
`deploy/` ; voir `deploy/README.md`.

## Règles que le code doit respecter

Elles ne sont pas des préférences : les enfreindre casse la raison d'être de
l'application.

- **Le périmètre, ce sont les dix-sept filiales.** Sénégal, Mali, Côte
  d'Ivoire, Madagascar, Cameroun, Gabon, Mauritanie, Burkina Faso, Niger,
  Bénin, Guinée, Togo, Gambie, Djibouti, Tchad, Congo, RDC : la liste est
  dans `backend/core/africa.py`, un pays se crée depuis elle et tout autre
  code est refusé. Au démarrage, seules la Côte d'Ivoire et le Togo sont
  créées ; les autres le seront à leur entrée dans le dispositif. Ouvrir une
  filiale demande de modifier ce fichier, donc une décision explicite.
- **Cinq rôles, pas un de plus.** Côté pays : `manager` saisit et soumet.
  Côté siège : `dm` (directeur manager) met en contrôle, `df` (directeur
  financier) constate — tous deux restrictibles à des pays ; `admin` (RH)
  tient les comptes, le référentiel, l'audit, les imports et exports, la
  réouverture ; `super_admin` (DG, DO, CEO, développeurs) peut tout. Il n'y
  a ni « direction des opérations » ni « auditeur » distincts. Un `manager`
  rattaché à des équipes ne voit que les leurs (`team__in`, sur le queryset,
  via `CountryScopedMixin.team_lookup`) ; sans équipe, tout son pays. La
  matrice vit dans `accounts/permissions.py` et nulle part ailleurs.
- **Le DM et le DF n'ont aucun droit d'administration.** Décision du
  produit : ils ne sont ni administrateurs ni super administrateurs. Ils
  gardent leurs seules fonctions de contrôle — `dm` dans `REVIEW_ROLES`,
  `df` dans `VALIDATION_ROLES` — et lisent l'historique du référentiel
  (`HISTORY_READ_ROLES`, `/api/history/`) sur leur périmètre. Ils ne
  figurent dans aucun autre ensemble : ni comptes, ni pays, ni référentiel,
  ni enveloppes, ni fichiers, ni réouverture, ni journal d'audit.
- **Les enveloppes sont l'affaire des super administrateurs.** Attribuer
  une enveloppe, demander, approuver ou refuser une réallocation, tenir les
  taux de change, valider un dépassement : `BUDGET_WRITE_ROLES` =
  `OVERRUN_APPROVERS` = `super_admin` seul. Le DF constate ce qui a été
  dépensé, il ne fixe pas ce qui peut l'être ; la RH tient les comptes, pas
  l'argent.
- **Le journal d'audit est l'affaire de la RH et de la direction.**
  `AUDIT_READ_ROLES` = `admin`, `super_admin`. Le journal relit les
  décisions du DM et du DF autant que celles des pays : cette relecture est
  un acte d'administration, pas de contrôle. L'historique du référentiel
  (`/api/history/`), lui, reste ouvert au siège entier.
- **Une dépense soumise est irréversible.** Elle ne revient pas au brouillon,
  ne se modifie plus, ne se supprime pas. Seul un brouillon — jamais soumis,
  donc sans valeur probante — peut être retiré par son auteur. **Une seule
  exception : la réouverture** (`reopen`, `REOPEN_ROLES` = `admin`,
  `super_admin`), motivée (`note`, gardée dans `Dossier.reopen_note`),
  tracée (`AuditLog` `reopened` sur le dossier et chaque ligne) et notifiée
  aux `dm` et `manager` du pays — elle sert à demander des comptes, jamais
  à corriger en silence. Les lignes reviennent en brouillon sans
  imputation. Un dossier dont une ligne est justifiée ou clôturée ne se
  rouvre pas : le siège a constaté.
- **Une dépense non justifiée pèse quand même sur l'enveloppe.** L'absence de
  preuve ne fait pas revenir l'argent ; elle se lit dans l'écart entre dépensé
  et justifié.
- **Rien ne se supprime, rien ne se purge**, hors brouillon. Le retrait
  d'une entité de référentiel se fait par désactivation (`is_active`) ;
  l'API répond 405 sur `DELETE`. La conservation est illimitée : ni tâche
  de ménage, ni rétention sur les dossiers, les pièces ou les journaux.
- **Les chiffres se calculent côté serveur.** Solde, écart, taux : l'interface
  affiche, elle ne recalcule pas.
- **Le cloisonnement par pays est vérifié sur le queryset**, pas seulement à
  l'affichage. Un objet hors périmètre répond 404, sans révéler son existence.
  Les écritures sont revalidées : une charge utile ne doit pas permettre de
  créer une entité chez le voisin.
- **Toute action sensible laisse une trace** dans `ChangeLog` ou `AuditLog` :
  qui, quoi, quand, depuis quelle adresse, ancienne et nouvelle valeur.
- **Le manager déclare, le DM contrôle, le DF constate.** Côté pays, seul
  le `manager` saisit et soumet. Au siège, le `dm` (directeur manager) met
  en contrôle (`review_expenses`), le `df` (directeur financier) justifie,
  refuse ou clôture (`validate_expenses`) ; `admin` (RH) et `super_admin`
  peuvent tout. Un manager ne justifie jamais une dépense, pas même la
  sienne. Et celui qui a saisi une dépense ne peut pas la justifier
  lui-même, fût-il au siège — il faut deux personnes.
- **La RH gère tous les pays.** Le référentiel d'un pays (équipes, projets,
  intitulés, catégories, bénéficiaires) est tenu par `admin` et
  `super_admin` sur tous les pays (`manage_subentities`) ; ni le `manager`,
  ni le `dm`, ni le `df` ne le modifient. `dm` et `df` sont des comptes du
  siège, restrictibles à des pays ; `admin` et `super_admin` sont toujours
  globaux.
- **Déclarer tient en une action.** Le manager remplit ses lignes, joint la
  pièce et soumet le dossier : ses lignes partent avec lui. Un dossier vide ne
  se soumet pas ; un dossier sans pièce se soumet avec un avertissement.
- **La double authentification est proposée, pas imposée** — décision
  reportée par la direction. `GET /api/me/` expose `totp_required`
  (politique du serveur, `DJANGO_TOTP_REQUIRED`, faux par défaut) et
  `totp_confirmed`. L'interface ne ferme la plateforme que si le premier
  est vrai et le second faux ; sinon elle propose l'enrôlement depuis le
  menu du compte. Un compte enrôlé présente son code à chaque connexion.
- **Un rejet exige un motif.** Une réouverture aussi.
- **Les fichiers entrent et sortent par les administrateurs.** L'import
  Excel et les exports (`xlsx`, `csv`, `docx`, `pdf` ; `year`, `month`
  facultatif, `country`) sont réservés à `EXPORT_ROLES` (`admin`,
  `super_admin`), lecture comprise ; tous les autres travaillent dans
  l'application, où chaque chiffre est calculé et chaque action tracée. Un
  total ne s'écrit qu'à devise unique.
- **Tout compte est protégé par une double authentification TOTP** et
  porte une adresse professionnelle (`ALLOWED_EMAIL_DOMAINS`, par défaut
  `innovpharma.net`). Un compte non enrôlé n'ouvre rien (`403
  totp_setup_required`), comme un mot de passe provisoire ; le jeton exige
  le `code` (`400 totp_required`) ; seul un administrateur réinitialise
  l'enrôlement (`reset-2fa`), et cela se trace (`totp_reset`). La clé
  `totp_secret` de `seed_users` n'existe que pour les environnements
  jetables.
- **L'interface est bilingue**, français et anglais : les textes passent par
  `gettext` côté serveur (un seul catalogue, `backend/locale/en`,
  `Accept-Language`, préférence `language` sur le profil ; notifications et
  e-mails dans la langue du destinataire) et par le dictionnaire de
  traduction côté client. Une chaîne en dur dans un composant est un défaut. Elle se sert sur le web et comme application de
  bureau installable (PWA) ; l'usage mobile n'est pas un cas prévu.
- **Une requête `GET` n'écrit rien.** Les alertes sont calculées à la
  lecture ; leur notification passe par `manage.py notify_alerts`, pour ne
  pas dépendre de quelqu'un qui ouvre une page. Une seule exception,
  assumée : le téléchargement d'un justificatif et les exports
  (`/api/exports/…`) écrivent une entrée `AuditLog`, parce qu'une donnée
  qui sort du système doit laisser une trace — c'est la règle « toute
  action sensible laisse une trace » qui l'emporte.

## Repères

| Sujet | Où |
|---|---|
| Modèle de données et décisions prises (référence, tenue à jour) | `docs/model-de-donnees.md` |
| États du circuit (`Status` et ses ensembles) | `backend/core/statuts.py` |
| Circuit de justification, réouverture | `backend/expenses/workflow.py` (états, prédicats), `backend/expenses/transitions.py` (services) |
| Services de transition (soumettre, rouvrir, trancher, clôturer, retirer un brouillon, contrôler une pièce) | `backend/expenses/transitions.py` |
| Services de réallocation (demander, approuver, refuser) | `backend/budget/transitions.py` |
| Refus métier (`RegleViolee`, `PermissionRefusee`, `HorsPerimetre`) et leur traduction HTTP | `backend/core/regles.py` |
| Rôles, périmètres, équipes, double authentification, authentification | `backend/accounts/` (`permissions.py`, `perimetre.py`, `scoping.py`, `views.py`) |
| API du référentiel (pays, équipes, projets…) et historique | `backend/accounts/referentiel.py` |
| Journaux `ChangeLog` et `AuditLog` : la seule porte d'écriture | `backend/core/journal.py` |
| Ordre des applications (`core < accounts < notifications < budget < expenses < reporting`) | `backend/core/tests/test_dependances.py` |
| Calculs budgétaires | `backend/budget/aggregates.py` |
| Interface | `DESIGN.md` |
| Serveur, supervision Grafana, sauvegardes | `deploy/README.md` |

## Conventions

- Le code, les commentaires et les messages de commit sont **en français**,
  comme l'interface — dont la version anglaise vient des catalogues de
  traduction, jamais d'un second jeu de composants.
- Le projet s'appelle **JUSTI INNOV**, pour INNOV PHARMA ; aucune autre
  marque n'apparaît dans le dépôt.
- Frontend sans point-virgule en fin de ligne, guillemets doubles.
- Un correctif s'accompagne du test qui l'aurait attrapé.

## Outillage Claude Code

Le dépôt embarque ce qu'il faut pour travailler dessus toujours de la même
façon ; servez-vous-en plutôt que de repartir de zéro.

| Besoin | Outil |
|---|---|
| Modifier le backend | skill `backend-django` |
| Modifier l'interface | skills `frontend-react` puis `design-system` |
| Relire avant de commiter | skill `revue-code`, agent `relecteur` |
| Chercher des bugs | agent `chasseur-de-bugs` |
| Comprendre le code sans le modifier | agent `explorateur-code` |
| Cadrer une évolution | agent `analyste-architecture` |
| Tout vérifier | skill `verifier` |
| Commiter, pousser, livrer | skill `livrer` |

Les agents vivent dans `.claude/agents/`, les skills dans `.claude/skills/`.
`.claudeignore` tient hors de vue dépendances, artefacts, données locales et
secrets. `.mcp.json` déclare le serveur MCP de CodeRabbit (jeton `GITHUB_PAT`
dans l'environnement, jamais dans le dépôt) et `.coderabbit.yaml` règle la
relecture automatique des pull requests, en français, sur les règles de ce
fichier.
