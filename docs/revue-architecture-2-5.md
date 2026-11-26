# Revue d'architecture majeure — version 2.5 (novembre 2026)

Revue du 26 novembre 2026, sur `main` 0cd6cf9 (version 2.4.11). La revue
précédente ([`revue-architecture-2026-11.md`](revue-architecture-2026-11.md),
version 2.4.1) confrontait le code aux principes SOLID et inventoriait les
index ; ses 24 écarts sont corrigés. Celle-ci regarde ce qu'elle laissait de
côté, sur cinq axes : **domaine et couches du backend**, **données,
calculs et montée en charge**, **sécurité (droits, cloisonnement,
authentification, traçabilité)**, **interface**, **exploitation, livraison,
tests et documentation**. La décision qui en sort est la **132** de
[`model-de-donnees.md`](model-de-donnees.md) ; ce fichier tient la liste
complète des écarts et leur état, pour qu'aucun ne se perde.

Méthode : lecture du code, des fichiers de déploiement et de la CI, sans
rien modifier ; mesures là où elles étaient possibles (tests, couverture et
poids de l'interface, mémoire des exports). **Chaque écart retenu a été
relu dans le code** avant d'entrer ici ; ceux qui n'ont pas tenu à la
relecture sont au § « Écartés ou rétrogradés ». Les gravités tiennent
compte de l'échelle annoncée — environ 600 lignes de dépense par an
(`infra-base-de-donnees.md`), sept en production à ce jour — et de deux
critères qui l'emportent sur la lenteur : **ce qui casse au lieu de
ralentir**, et **ce qui touche à la preuve**.

## Verdict d'ensemble

Le verdict de la 2.4.1 tient : un **monolithe modulaire** sain, à garder,
sans découpage en services ni nouvelle application dans `expenses`. Le
circuit, la matrice des capacités, le journal unique et ses déclencheurs,
la carte des index et les garde-fous de contrat (schéma d'API, types
générés, catalogue anglais) sont solides.

Ce qui manque n'est plus de la structure de code, mais **des garanties qui
tiennent par construction plutôt que par discipline** : des règles
probantes vérifiées dans le seul sérialiseur, un cloisonnement que seul le
routeur DRF garantit, un journal immuable pour le rôle applicatif mais pas
pour le propriétaire de la base, des pièces qu'on restaure moins bien que
la base, un retour arrière qui suppose une compatibilité que rien ne
vérifie, et une panne que personne n'apprendrait. Pour une équipe d'une
personne, c'est là que se joue la suite : ce que la machine ne garde pas,
personne ne le garde.

**54 écarts** : 8 majeurs, 26 moyens, 20 mineurs. Aucun n'est corrigé dans
la 2.5.0, qui ouvre le cycle ; les lots sont au § « Ordre de traitement ».

## Déjà solide

- **Le journal** : une seule porte d'écriture (`core/journal.py`, gardée par
  `test_journal_unique`), des déclencheurs qui refusent `UPDATE` et
  `DELETE` sur `AuditLog`, `ChangeLog` et `ElementSupprime`.
- **La matrice** : verrous appliqués à la lecture (`roles_effectifs`) et
  revalidés à l'enregistrement depuis les mêmes attributs ; `RolePermission`
  refuse une écriture sans capacité déclarée.
- **Le cloisonnement des routeurs** : `accounts/tests/test_traversee.py`
  génère la traversée depuis les quatre routeurs ; les clés étrangères des
  charges utiles passent par `ChampCloisonne` ; hors périmètre, 404.
- **L'authentification** : verrous de profil, de mot de passe provisoire et
  de double authentification en middleware, avant toute vue ; débit limité
  par adresse et par compte ; code TOTP à usage unique ; jeton révoqué à
  chaque changement sensible.
- **La concurrence** : numérotation sous verrou, ordre dossier › ligne ›
  enveloppe, contraintes d'unicité en garde derrière.
- **Le contrat d'API** : types TypeScript générés depuis `docs/api/schema.json`,
  diff vérifié par la CI ; un seul point d'accès (`lib/api.ts`) ; aucune
  comparaison de rôle dans l'interface ; `allowed_actions` lu, pas recalculé
  (`lib/rien-ne-se-calcule.test.ts`).
- **Le stockage des pièces** : aucun fichier effacé dans une transaction,
  inventaire des orphelins, empreinte de chaque fiche confrontée à son
  fichier par `verifier_restauration`, service worker en `NetworkOnly` sur
  `/api/`.
- **La livraison** : actions épinglées par SHA, Dependabot sur six
  écosystèmes, marque `ENVIRONNEMENT`, retour automatique à l'étiquette
  précédente, reprise à un instant donné rejouée par la CI sur la pile de
  production et répétée sur le serveur.
- **Les chiffres** : 1 631 tests backend (28 072 lignes pour 25 471 de
  code), 634 tests d'interface (couverture 71,7 % des lignes), CI d'environ
  7 min 30.

## Les 54 écarts

Gravité : **M** majeur, **m** moyen, **–** mineur. Effort : S (quelques
heures), M (un à trois jours), L (plus). État : **à faire** tant qu'aucune
version ne l'a corrigé ; la colonne se tient à jour comme celle de la revue
2.4.1.

### A. Règles probantes et domaine

| N° | Grav. | Écart | Où | Correction | Effort | État |
|---|---|---|---|---|---|---|
| 1 | M | **Des règles probantes ne sont vérifiées que par le sérialiseur** : le motif d'un rejet de pièce (le service `controler_piece` l'accepte vide, alors que les autres refus motivés sont vérifiés dans leur service) ; la devise et le fuseau d'un pays (`seed_users`, chemin de production des pays, accepte toute devise de trois lettres et retombe sur `UTC` si le fuseau manque — l'incident de la décision 128) ; l'immuabilité du pays, du projet et du type d'un dossier | `expenses/controle_des_pieces.py`, `core/models.py` (`timezone` `default="UTC"`), `accounts/management/commands/seed_users.py`, `expenses/serializers.py` (`verifier_le_deplacement`) | Le motif exigé dans le service ; validateur de devise sur le champ et `Country.clean()` qui exige un fuseau de `FUSEAUX[code]`, défaut `UTC` retiré ; déclencheur `BEFORE UPDATE` sur `country_id`, `project_id`, `kind_id` du dossier | S | à faire |
| 2 | m | **Le projet, rubrique principale, n'a ni service ni `allowed_actions`** : création, typage, renommage et complétion sont orchestrés dans la vue ; `seed_demo` et `seed_recette` recopient l'enchaînement sans la règle « un projet sans dossier ne se crée pas » ; `ProjectSerializer` vit dans `core`, d'où il ne lit pas la matrice, et l'interface recalcule les droits (`can("corbeille.supprimer") && me.workflow.suppressions_ouvertes && !projet.is_historical`) | `expenses/projets.py`, `core/serializers.py`, `frontend/src/pages/projets/detail.tsx`, `components/projects/*` | Services `ouvrir_projet`, `renommer_projet`, `modifier_projet`, `completer_projet` ; `ProjectSerializer` dans `expenses` avec `allowed_actions` calculé par `workflow` ; l'interface et les jeux d'essai passent par eux | M | à faire |
| 3 | m | **« Clôturé, plus rien ne bouge » n'est pas gardé sur la ligne** : une transition de ligne ne verrouille que la ligne et ignore l'état du dossier, comme `expense_allowed_actions`. Aucun chemin des services n'y mène aujourd'hui (un dossier ne se clôt que justifié, donc sans ligne non justifiée), mais l'invariant tient par l'enchaînement de deux transitions, pas par une vérification | `expenses/circuit.py` (`_verrouiller_la_ligne`, `_avant_sur_la_ligne`), `expenses/workflow.py` | Verrouiller le dossier puis la ligne ; refuser toute transition de ligne d'un dossier clôturé ; même filtre dans `allowed_actions` ; test | S | à faire |
| 4 | m | **« Déjà déclaré » se lit dans le journal** : `a_ete_declare` cherche une entrée `submitted` par `object_type="Expense"` (le nom d'une classe), et pour un dossier `bool(reopen_note)`. Un droit (retrait d'un brouillon, soumission des lignes d'un collègue) dépend d'une ligne de journal | `expenses/workflow.py`, `expenses/models.py` (`with_rectification`) | `Expense.declaree_le`, `Dossier.declare_le`, repris du premier `submitted` du journal ; `CHECK (status = 'draft' OR declaree_le IS NOT NULL)` | S/M | à faire |
| 5 | m | **Les copies de contexte ne sont liées par rien en base** : `Expense.country`, `Expense.project`, `Proof.dossier` ne sont vérifiées qu'à l'écriture, et chaque liste se cloisonne sur une copie différente (lignes sur `country`/`team`, pièces sur `dossier__…`, rectifications sur `expense__…`) | `expenses/models.py`, `expenses/views.py` | Clés étrangères composées (`UNIQUE (id, country_id)` sur le dossier, `(dossier_id, country_id)` depuis la ligne ; idem ligne › pièce), précédées d'une requête de contrôle sur une copie de la production ; décider quel champ cloisonne une pièce | M | à faire |
| 6 | m | **Invariants simples absents de la base** : 20 colonnes à `choices` pour 12 `CheckConstraint`, aucune sur une valeur ; manquent notamment pièce rejetée ⇒ motif, rectification décidée ⇒ décideur, dossier prédéfini ⇒ type, rang et projet ; `Dossier.project` reste nullable « le temps de la reprise », faite depuis | `expenses/models.py` | Une migration de contraintes, précédée d'une requête de contrôle (les lignes d'avant le §7 peuvent ne pas avoir d'auteur) | S/M | à faire |
| 7 | – | **Champs sans effet** : `Project.budget`, modifiable par l'administrateur et affiché comme un montant, n'est lu nulle part (ni serveur ni BI) alors que les vraies enveloppes de projet sont au `super_admin` ; `Project.status` n'est lu nulle part ; `CostCenter` n'est référencé par rien | `core/models.py`, `frontend/src/components/projects/edit-project.tsx` | Décision de la direction : figer en lecture et masquer, ou archiver les valeurs au `ChangeLog` puis retirer (retirer une colonne qui porte des valeurs est une purge) | S | à faire |
| 8 | – | **`AuditLog` vit dans `expenses`, mais `core` y écrit par son nom** (`apps.get_model`, invisible au test d'ordre) ; `budget` recopie les valeurs d'action et duplique `Resultat` | `core/journal.py`, `budget/transitions.py`, `expenses/exigences.py` | Modèle déplacé dans `core` sous la même table (`SeparateDatabaseAndState`) ; `Resultat` dans `core` | M | à faire |
| 9 | – | **`reporting` sert de fourre-tout** : l'import (901 lignes) est une écriture ; les jeux d'essai et les commandes d'exploitation y vivent ; la restitution proprement dite fait environ 2 050 lignes sur 5 163. `expenses/serializers.py` fait 1 309 lignes | `reporting/imports.py`, `reporting/management/commands/` | Import dans `expenses` ; application `outillage` au-dessus de `reporting` pour seeds et commandes ; sérialiseurs découpés par sujet comme la décision 131 | M | à faire |
| 10 | – | **Code mort et docstrings périmées** : la branche « dossier » de `retirer_brouillon` est inatteignable par l'API mais appelable, et supprimerait un dossier prédéfini (contre la décision 106) ; alias `ALWAYS_GLOBAL_ROLES` ; `createDossier` dans l'interface vise une route qui répond 405 ; docstrings qui décrivent l'avant-2.0 (`accounts/models.py:26-38`, `expenses/models.py`) | `expenses/retrait.py`, `accounts/models.py`, `frontend/src/lib/expenses.ts` | Retirer ; `retirer_brouillon` refuse un dossier ; `services.py` renommé `imputation.py` | S | à faire |

### B. Données, calculs et montée en charge

| N° | Grav. | Écart | Où | Correction | Effort | État |
|---|---|---|---|---|---|---|
| 11 | M | **Les pièces ne suivent pas la reprise de la base** : la base perd au plus 5 minutes (archivage continu), les pièces jusqu'à 24 h (miroir quotidien à 02:15) ; la réplique ne reçoit aucune pièce et rien n'en parle dans sa procédure. Serveur perdu à 18 h : chaque pièce du jour a sa fiche, son empreinte et sa trace — et plus de fichier | `deploy/docker-compose.prod.yml` (`SAUVEGARDE_PIECES_HEURE`), `deploy/docker-compose.replique.yml`, `deploy/README.md` (tableau « Objectifs ») | Écrire le RPO des pièces ; miroir continu (réplication de seau MinIO ou `mc mirror --watch`) vers la réplique et le distant ; la promotion compte objets et fiches avant d'ouvrir | M | à faire |
| 12 | m | **Exports tabulaires construits en mémoire, sans plafond** : mesuré hors ORM, un export Word coûte environ 26 Mo et 2 s par millier de lignes et dépasse le `mem_limit` de 768 Mo vers 25 000 lignes ; xlsx 676 Mo à 120 000. L'échec tue le worker et ses autres requêtes. Le PDF a son plafond, pas les autres | `reporting/exports.py`, `reporting/views.py` | Plafond par format (400 « restreignez au mois ou au pays »), `Workbook(write_only=True)`, CSV en flux | M | à faire |
| 13 | m | **Bornes en UTC dès que plusieurs pays se lisent ensemble** : exports consolidés, alertes de l'ordonnanceur et année par défaut des vues bornent en UTC ; le fuseau d'un pays se lit de six façons, dont quatre se replient sur UTC. Une dépense de Djibouti du 1er janvier à 02 h locale est en N+1 pour l'enveloppe et le BI, en N dans l'export consolidé | `reporting/scope.py`, `reporting/views.py`, `reporting/management/commands/notify_alerts.py`, `expenses/services.py`, `expenses/serializers.py` | Bornes par pays même en lecture consolidée (le motif existe dans `reporting/alerts.py`) ; une propriété `Country.fuseau` qui lève au lieu de se replier ; révise l'exception consignée à la décision 122 | S | à faire |
| 14 | m | **La parité du BI ne couvre ni l'exercice clos, ni les fuseaux décalés, ni sept vues** : le décor ne joue que l'année courante et le Togo (UTC+0) ; `delais`, `pieces`, `rectifications`, `reallocations`, `doublons`, `comptes`, `journal` ne sont comparées à rien ; `bi.journal.jour` tronque dans le fuseau de la session Grafana, que le rôle ne fixe pas ; la recherche du taux est copiée trois fois en SQL | `reporting/tests/test_bi.py`, `reporting/bi/vues.sql`, `deploy/creer_role_bi.sql` | Exercice clos et Djibouti (UTC+3) près de minuit dans le décor ; parité de chaque vue ; fuseau fixé sur `justi_bi` ; fonction `bi.taux_au` | M | à faire |
| 15 | m | **Bénéficiaires plafonnés à 200 dans la saisie** : la fiche dossier les charge par page de 200 et les propose en liste déroulante ; un bénéficiaire ne se supprime pas. Au 201e, « au profit de qui » se dégrade (doublon ou champ vide) | `frontend/src/pages/dossiers/detail.tsx`, `components/expenses/expense-form.tsx`, `lib/referentiel.ts` | Champ à recherche côté serveur (`?search=`), composant partagé ; revoir chaque `REFERENTIEL_PAGE_SIZE` posé sur une table qui grossit | M | à faire |
| 16 | – | **Règles recopiées dans le backend** : « pièce exploitable » huit fois (`expenses/models.py` ×5, `serializers.py`, `corbeille.py`, `alerts.py`, plus `bi/__init__.py`), dont une seconde implémentation de `has_proof` ; « engagé ou consommé » trois fois ; le consolidé du tableau de bord calculé deux fois, différemment (jusqu'à un centime d'écart par pays avec Grafana) | `expenses/`, `reporting/pilotage.py`, `budget/aggregates.py` | `Proof.INUTILISABLES`, `ProofQuerySet.exploitables()`, `DECLARED_STATUSES` ; `totals` dérivé de `consolidated` | S | à faire |
| 17 | – | **Numéros réutilisés si la corbeille rouvre après la mise en ligne** : `Max(sequence)+1` ; un numéro figé dans le journal et les notifications désignerait deux objets | `core/numerotation.py`, `expenses/numerotation.py` | Fermeture définitive de la corbeille (`fermee_le`, irréversible) à la mise en ligne, ou compteur monotone | S | à faire |
| 18 | – | **Ordres de verrous opposés sur les enveloppes** : la soumission verrouille dans l'ordre du modèle (`-pk`), l'approbation d'une réallocation par identifiant croissant ; interblocage possible, rare, non testé | `expenses/circuit.py`, `budget/transitions.py` | `.order_by("pk")` explicite ; test à deux fils | S | à faire |
| 19 | – | **Le verrou du dossier est tenu pendant l'écriture S3** : avec un MinIO lent, jusqu'à environ 26 s ; une soumission concurrente échoue en 503 | `expenses/views.py`, `expenses/pieces.py` | Écrire l'objet avant la transaction sous un nom unique, puis verrouiller et insérer | S/M | à faire |
| 20 | – | **Vues BI qui relisent tout l'historique** : année calculée (aucun index), `delais` agrège tout le journal ; négligeable à l'échelle attendue, non mesuré au banc | `reporting/bi/vues.sql` | Mesurer les six tableaux au banc par `mesurer_les_temps` ; vue matérialisée si besoin | S | à faire |
| 21 | – | **Pas de doctrine des migrations sur les grosses tables** : 62 migrations, aucune `AddIndexConcurrently` ; un index sur le journal bloquerait les écritures. Ne pas squasher (les `RunSQL` des déclencheurs ne s'élident pas) | `*/migrations/` | Consigner : index de journal en `AddIndexConcurrently` (`atomic = False`), migrations de données par lots, `migrate` chronométré dans la restauration isolée | S | à faire |

### C. Sécurité : droits, cloisonnement, authentification, traçabilité

| N° | Grav. | Écart | Où | Correction | Effort | État |
|---|---|---|---|---|---|---|
| 22 | M | **Le Grafana de supervision est servi sur l'origine de l'application** (`/grafana/`, profil `supervision`), directement par Caddy, sans la CSP de nginx, sans SameSite strict ni durée de session — alors que le jeton vit dans `localStorage` et que `lib/api.ts` dit lui-même que la CSP est ce qui le protège. Une faille XSS de Grafana lirait le jeton de qui suit un lien ; le Grafana BI, lui, a son origine propre | `deploy/Caddyfile`, `deploy/docker-compose.prod.yml`, `frontend/src/lib/api.ts` | Supervision sur son propre nom (`supervision.<domaine>`) ou par tunnel seulement, avec les réglages du BI ; test : aucun `reverse_proxy` autre que `frontend` sous le domaine de l'application | S | à faire |
| 23 | M | **Le journal n'est immuable que pour qui ne possède pas la base** : déclencheurs `FOR EACH ROW` sans `BEFORE TRUNCATE` ; par défaut le service se connecte en propriétaire et rien ne vérifie au démarrage qu'il ne l'est pas ; même avec `justi_app`, le secret du propriétaire reste monté dans le backend et l'ordonnanceur | `expenses/migrations/0008`, `core/migrations/0009`, `expenses/migrations/0023`, `deploy/docker-compose.prod.yml`, `backend/entrypoint.sh` | Déclencheurs `BEFORE TRUNCATE` ; hors debug, refuser de démarrer si l'utilisateur courant possède les tables (et le dire dans `/api/health/`) ; migrations jouées par un conteneur ponctuel, secret retiré des services permanents ; à décider : chaînage des entrées par empreinte | M | à faire |
| 24 | m | **Rien n'oblige une vue à déclarer sa capacité** : la permission par défaut est `IsAuthenticated` ; une vue qui oublie `permission_classes` est ouverte en écriture à tous ; aucun test n'énumère les routes | `config/settings.py`, `accounts/permissions.py` | `RolePermission` par défaut, marqueur explicite des vues du titulaire (`me`, mot de passe, 2FA) ; test sur `get_resolver()` | S | à faire |
| 25 | m | **La traversée du cloisonnement ne couvre que les routeurs** : tableau de bord, répartition, neuf exports, import et actions de liste (`register`, `summary`, `par-pays`, `synthese`) ont des tests écrits à la main — couverts aujourd'hui, rien n'y oblige demain | `accounts/tests/test_traversee.py`, `reporting/urls.py` | Parcourir `get_resolver()` : chaque GET sous `/api/` avec un manager d'un autre pays, avec et sans `?country=` ; exceptions nommées | M | à faire |
| 26 | m | **Les services ne revérifient qu'à moitié périmètre et capacité** : seuls trois services appellent `exiger_dans_le_perimetre` ; le tronc du circuit, le contrôle des pièces, le retrait, la saisie et le dépôt ne le font pas ; la saisie, le dépôt et l'import ne vérifient pas non plus leur capacité. Neuf réécritures du prédicat de périmètre échappent au test structurel (son expression ne voit ni `pk__in=` ni `dossiers__team_id__in`) — toutes justes aujourd'hui | `expenses/circuit.py`, `controle_des_pieces.py`, `retrait.py`, `saisie.py`, `pieces.py`, `reporting/imports.py`, `accounts/tests/test_perimetre_unique.py` | Chaque service exige périmètre et capacité (décision 124 étendue) ; test structurel élargi à `access.country_ids`, `team_ids`, `has_global_scope` hors de `perimetre.py` | M | à faire |
| 27 | m | **La séparation des tâches se contourne par la gestion des comptes** : l'`admin` pose le mot de passe provisoire d'un `manager` (et le connaît), peut s'y connecter, déclarer, puis contrôler sous son nom ; entre pairs, un `admin` réinitialise le mot de passe et la 2FA d'un autre `admin`. Tout est tracé, rien ne relie les traces | `accounts/serializers.py`, `accounts/views.py`, `accounts/permissions.py` | Décision de la direction : réinitialisation d'un `admin` réservée au `super_admin`, titulaire notifié, et signalement par `synthese_audit` d'une décision sur une ligne d'un compte récemment créé ou réinitialisé par le décideur | M | à faire |
| 28 | m | **Secrets d'authentification en clair en base** : `Token.key` et `totp_secret` ; une lecture du schéma (pgAdmin en propriétaire, sauvegarde déchiffrée) donne 30 jours de sessions et les générateurs TOTP | `accounts/authentication.py`, `accounts/models.py` | Empreinte du jeton (recherche par préfixe), `totp_secret` chiffré par une clé hors base ; tous les jetons révoqués à la livraison | M | à faire |
| 29 | m | **Session longue et partagée, enrôlement sur simple jeton** : jeton unique par compte, 30 jours sans délai d'inactivité, rendu à chaque connexion (une déconnexion coupe tous les postes) ; `/me/2fa/enrol/` n'exige que le jeton — un jeton volé enrôle son propre authentificateur | `accounts/authentication.py`, `accounts/views.py` | Mot de passe exigé pour enrôler ; délai d'inactivité ; durée raccourcie pour `admin` et `super_admin` ; jeton par appareil | M | à faire |
| 30 | – | **Course dans le mémo de la matrice** : empreinte et matrice écrites l'une après l'autre dans un dictionnaire partagé par les quatre fils d'un worker ; un entrelacement associe l'empreinte neuve à la matrice ancienne, et un droit retiré survit dans ce worker (les verrous tiennent) | `accounts/permissions.py` (`_MEMO_MATRICE`) | Une seule affectation atomique d'un tuple, relue dans une variable locale | S | à faire |
| 31 | – | **Grafana hors de l'annuaire** : le BI s'ouvre au mot de passe seul, depuis toute adresse par défaut (`BI_IP_AUTORISEES` vaut `0.0.0.0/0`) ; les deux Grafana partagent `GRAFANA_ADMIN_PASSWORD` ; désactiver un compte JUSTI ne ferme pas le BI | `deploy/caddy/bi-1.caddy`, `deploy/docker-compose.prod.yml` | Restriction par adresse obligatoire en production, un mot de passe par Grafana, procédure de départ couvrant les trois annuaires | S | à faire |
| 32 | – | **Surface et traces secondaires** : refus 403/404 jamais comptés (un manager qui sonde le pays voisin est invisible) ; pas de délai croissant après échecs de connexion (≈ 7 200 essais par jour sur un compte) ; `SessionAuthentication` et `CORS_ALLOW_CREDENTIALS` actifs en production sans usage ; `postgres-exporter` sur le rôle applicatif | `core/regles.py`, `config/settings.py`, `deploy/docker-compose.prod.yml` | Compteur des refus ; délai croissant par compte et notification ; réglages réservés au debug ; rôle `justi_monitor` (`pg_monitor`) | S | à faire |

### D. Interface

| N° | Grav. | Écart | Où | Correction | Effort | État |
|---|---|---|---|---|---|---|
| 33 | m | **Le lien URL › réponse › charge utile › filtres est écrit à la main** : `apiGet<T>(url: string, params?: Record<string, unknown>)`, 36 charges `unknown`, 24 filtres non typés ; seules les formes des réponses sont gardées par la CI. Un filtre renommé côté serveur est ignoré, et la liste revient non filtrée en se disant filtrée | `frontend/src/lib/api.ts`, `lib/*.ts`, `lib/types.ts` | Client typé par `paths` (surcouche maison qui déduit réponse, corps et paramètres) ; alias `*TransitionResponse` au lieu des intersections recopiées | M | à faire |
| 34 | m | **Session non synchronisée entre onglets, profil jamais relu** : après une reconnexion sous un autre compte dans un onglet, l'autre garde menu, `can()` et caches du premier en envoyant le jeton du second ; une matrice modifiée ne se voit qu'au rechargement | `frontend/src/context/auth.tsx`, `lib/referentiel.ts` | Écouter `storage` sur le jeton (session effacée, rechargement) ; relire `me` au retour de visibilité | S | à faire |
| 35 | m | **Le `super_admin` n'est jamais parcouru par les captures** : la CI ne crée qu'un `admin` et un `manager` ; enveloppes, réallocations, taux, types de projets, corbeille et lien BI ne sont jamais rendus en CI (ni axe, ni console) ; `pages/budgets/list.tsx` à 0 % de couverture | `.github/workflows/ci.yml`, `frontend/scripts/screenshot.ts` | Comptes `super_admin` de CI (deux, pour « nul ne tranche sa propre réallocation ») et section de capture ; tests vitest des enveloppes | M | à faire |
| 36 | m | **Une panne s'affiche « introuvable »** : `useQuery` ne garde que le message ; les fiches dossier, projet et pays disent « n'existe pas ou n'est pas dans votre périmètre » quand le serveur est injoignable, sans « Réessayer » | `frontend/src/lib/use-query.ts`, `pages/dossiers/detail.tsx`, `pages/projets/detail.tsx`, `pages/countries/detail.tsx` | Statut exposé dans `QueryResult` ; état partagé : 404 introuvable, 0/5xx indisponible avec « Réessayer » | S | à faire |
| 37 | m | **Règles et listes recopiées côté client** : le groupe « à contrôler » écrit deux fois en dur ; la règle des équipes (`lib/teams.ts`) et celle de la répartition réécrites ; la devise de consolidation `"XOF"` encore en dur dans « Enveloppes » (l'écart 4 de la 2.4.1 n'avait corrigé que le pilotage) ; huit listes de `lib/labels.ts` non comparées au schéma (à jour aujourd'hui) | `pages/register/index.tsx`, `pages/dashboard/index.tsx`, `pages/budgets/list.tsx`, `lib/teams.ts`, `lib/labels.ts` | Filtre serveur `a_controler`, équipes saisissables exposées par le serveur, `currency` renvoyé ; test des listes contre `components.schemas.*Enum` | S/M | à faire |
| 38 | – | **Deux caches maison à clés libres** : la clé `"countries"` recopiée à six endroits sans ses paramètres, un prédicat d'invalidation copié trois fois, la matrice en cache jamais invalidée | `lib/use-query.ts`, `lib/referentiel.ts`, `pages/projets/*`, `pages/configuration/users-section.tsx` | Registre de clés et hooks par ressource, sur le modèle de `useTypesDeProjets` (pas de nouvelle dépendance) | M | à faire |
| 39 | – | **Gros fichiers qui mêlent données, règles et rendu** : `pages/dashboard/index.tsx` 793 lignes, `project-types-section.tsx` 638 (15 `useState`), `general-section.tsx` 513, `projets/list.tsx` 488 | `frontend/src/pages/` | Comme l'écart 23 de la 2.4.1 : `usePilotage()`, `NouveauProjetDialog` à part, types de projets et types de dossiers séparés | M | à faire |
| 40 | – | **Finitions** : 30 clés de traduction orphelines sur 1 265, chaînes en dur détectées seulement si accentuées, manifeste PWA en français seul ; `KNOWN_FIELDS` double `champs.*` ; une seule frontière d'erreur, sans remise à zéro ; 263 Ko compressés avant la connexion (les deux langues chargées) sans budget en CI ; couverture ni publiée ni plafonnée | `frontend/src/i18n/`, `lib/api.ts`, `App.tsx`, `vite.config.ts` | Test des clés orphelines ; `i18next.exists` ; frontière autour de `<Outlet/>` avec `key={pathname}` ; `AppLayout` paresseux et langue active seule ; seuils de poids et de couverture | S | à faire |

### E. Exploitation, livraison, tests et documentation

| N° | Grav. | Écart | Où | Correction | Effort | État |
|---|---|---|---|---|---|---|
| 41 | M | **Une panne de production ne serait signalée à personne** : supervision désactivée par défaut, aucune alerte avec destinataire (décision 130), e-mail coupé (décision 88), aucune sonde externe ; une sauvegarde manquée ne se voit que dans la cloche d'un compte `admin` | `deploy/README.md`, `docs/model-de-donnees.md` (130) | Workflow GitHub planifié qui interroge `/api/health/` (fraîcheur des sauvegardes comprise) et ouvre ou referme un ticket, comme l'alerte de livraison — aucun courrier ne part de la plateforme | S | à faire |
| 42 | M | **Le retour arrière automatique suppose une compatibilité que rien ne garantit** : le README affirme qu'un code N-1 lit et écrit un schéma N « tant que la migration n'a fait qu'ajouter » ; or 18 `AddField` non nuls n'ont pas de `db_default` (Django retire le défaut en base), dont `changelog.motif` et `dossier.predefini` — après un retour, le code N-1 n'insère plus dans ces tables. La branche de retour de `deploy.sh` n'a aucun test | `deploy/README.md`, `*/migrations/`, `deploy/deploy.sh` | Test qui exige `db_default` (ou `null=True`) sur tout `AddField` non nul ajouté après une date pivot ; test shell de `deploy.sh` dont le `--wait` échoue | M | à faire |
| 43 | M | **La livraison de production rejoue la CI et reconstruit les images** d'un commit déjà vérifié : la v2.4.9, verte sur `main`, a échoué sur son étiquette (capture instable) et a dû devenir une v2.4.10 ; l'image backend est construite trois fois, et l'image livrée n'est pas celle qui a passé le parcours | `.github/workflows/cd.yml`, `ci.yml` | Sur une étiquette : vérifier qu'une exécution verte existe pour ce SHA, puis réétiqueter l'image `sha-…` publiée (`imagetools create`) ; le parcours tourne sur les images construites | M | à faire |
| 44 | M | **Réplique, aiguillage et promotion n'ont jamais tourné sur deux vraies machines** (le README le dit), mais `infra-base-de-donnees.md` présente l'option C « mise en place » ; environ 1 250 lignes de scripts, compose et tests, et 360 lignes de README, à entretenir seul | `deploy/`, `docs/infra-base-de-donnees.md`, `backend/core/tests/test_replique.py`, `test_balanceur.py` | Dire « écrite, non éprouvée » ; ranger cette pile à part (`deploy/haute-disponibilite/`) jusqu'à la première répétition ; garder le tunnel et la reprise à un instant donné | S | à faire |
| 45 | m | **Les fichiers de `deploy/` du serveur peuvent diverger du code livré** sans contrôle (la v1.3.1 tournait encore sur Postgres 16.4) | `deploy/deploy.sh`, `deploy/justi-livrer` | Empreinte de `deploy/` inscrite dans un label de l'image ; `deploy.sh` la compare et avertit | S | à faire |
| 46 | m | **Les tests ne tournent pas sur le Python de production** (CI 3.12, image 3.15) ; dépendances transitives non verrouillées ; images de base par étiquette, sans digest | `.github/workflows/ci.yml`, `backend/Dockerfile`, `backend/requirements.txt` | CI, mypy et ruff sur 3.15 ; verrou avec empreintes (`pip-compile --generate-hashes`) ; images par digest (Dependabot les relève) | M | à faire |
| 47 | m | **`model-de-donnees.md` §8 n'est plus navigable** : 219 Ko, 131 décisions dans un seul tableau (cellule médiane 1 089 caractères, maximum 12 685) ; deux seulement disent qu'elles sont révisées ; la décision 3 (« pièces au niveau du dossier ») contredit la 107 sans renvoi | `docs/model-de-donnees.md` | Colonne « Statut » (en vigueur / révisée par N / remplacée par N), index par thème, une phrase par décision et le récit dans `docs/decisions/NNN.md` | M | à faire |
| 48 | m | **La documentation se contredit** : `deploy/README.md` dit `deploy/` « copié à chaque livraison » puis « la livraison ne touche pas aux fichiers » (même contradiction dans `cd.yml`) ; `verifier_sauvegardes` annonce un e-mail que la décision 88 coupe ; `CLAUDE.md` ne cite pas `redis` ; « Vérifier » ne liste ni `makemigrations --check`, ni le diff du schéma, ni le catalogue, ni `npm run build`, que la CI impose | `deploy/README.md`, `.github/workflows/cd.yml`, `reporting/management/commands/verifier_sauvegardes.py`, `CLAUDE.md` | Corriger les phrases ; un seul script de vérification appelé par la CI, `CLAUDE.md` et les skills | S | à faire |
| 49 | m | **Des tests d'infrastructure figent du texte, au mauvais endroit** : onze fichiers de tests backend lisent `deploy/` ou le README (`assertIn` sur des phrases, directives Caddy littérales) et ne trouvent `deploy/` que par un montage | `backend/core/tests/test_replique.py`, `test_balanceur.py`, `test_caddy.py`, `test_tls.py`… | Dans `deploy/tests` : `caddy validate`, `compose config`, scripts sous doublures ; plus d'assertion sur le README | M | à faire |
| 50 | m | **Aucun test bout en bout du circuit** : les captures vérifient droits, navigation et accessibilité, mais aucune soumission, justification ni clôture ne passe par l'interface | `frontend/scripts/screenshot.ts` | Un parcours Playwright : le manager dépose et soumet, l'admin met en contrôle, justifie, clôture | M | à faire |
| 51 | – | **L'audit des dépendances bloque la livraison** : un avis publié entre la fusion et l'étiquette bloque un correctif urgent ; `pip-audit` non épinglé | `.github/workflows/ci.yml`, `cd.yml` | Bloquant sur les PR, ticket sans blocage dans la livraison ; version épinglée | S | à faire |
| 52 | – | **La voie Railway est entretenue mais morte** (refusée par Railway, décision 48 ; sans BI ni rétention conforme) : `backend/railway*.json`, branche `DEPLOIEMENT_SSH` de `cd.yml`, gabarit nginx | `docs/deploiement-railway.md`, `backend/railway*.json`, `.github/workflows/cd.yml` | Marquer abandonnée en §8 et retirer | S | à faire |
| 53 | – | **Le retour arrière manuel exige root et un jeton personnel** : le déclenchement manuel ne prend aucune étiquette ; le serveur n'en garde que deux | `.github/workflows/cd.yml`, `deploy/deploy.sh` | Entrée `etiquette` au déclenchement manuel, sans CI ni build, sous l'approbation de l'environnement | S | à faire |
| 54 | – | **`CLAUDE.md` est lourd et redondant ; shellcheck limité aux erreurs** : 442 lignes chargées à chaque session, double authentification dite deux fois, partage des rôles trois fois ; `shellcheck --severity=error` sur 3 156 lignes de shell, version non fixée | `CLAUDE.md`, `.github/workflows/ci.yml` | Fusionner les doublons, renvoyer aux décisions ; shellcheck à `warning` sur les scripts de sauvegarde et de livraison, épinglé | S | à faire |

## Ordre de traitement

Chaque lot est une version 2.5.x, avec sa décision au §8 et le test qui
aurait attrapé chaque écart. L'ordre suit le risque, puis l'effort.

1. **2.5.1 — Avant l'ouverture aux filiales** (tout en S) : 22 (Grafana
   hors de l'origine), 23 sans le chaînage (`TRUNCATE`, refus de démarrer
   en propriétaire), 41 (alerte par ticket), 1 (règles probantes dans le
   modèle et le service), 24 (`RolePermission` par défaut), 30 (mémo),
   3 (clôture gardée sur la ligne), 36 (panne ≠ introuvable), 34 (onglets),
   48 (contradictions).
2. **2.5.2 — Livrer et revenir en arrière sans crainte** : 42, 43, 45, 51,
   53, puis 46.
3. **2.5.3 — Le cloisonnement par construction** : 26, 25, 2 (services et
   `allowed_actions` du projet ; l'écran change, le guide « Ouvrir un
   projet » se filme de nouveau), 37.
4. **2.5.4 — Les données et la preuve** : 11 (pièces), 12 (exports),
   13 (bornes par pays), 14 (parité BI), 16, 4, 6, puis 5 (clés composées,
   après une requête de contrôle sur une copie de la production).
5. **2.5.5 — Session et secrets**, en une livraison qui reconnecte tout le
   monde : 28, 29.
6. **2.5.6 — Interface** : 33, 35, 15, 38, 39, 40.
7. **2.5.7 — Ranger** : 44, 52, 49, 50, 47, 54, 8, 9, 10, puis les mineurs
   restants (17 à 21, 31, 32).

## Ce qui attend la direction

Ces écarts ne se corrigent pas sans une décision qui n'appartient pas au
code :

- **27** — ce que l'on retient contre l'usurpation d'un compte par
  l'administration (réinitialisation d'un `admin`, signalements).
- **7** — le sort de `Project.budget`, `Project.status` et `CostCenter`.
- **17** — la fermeture *définitive* de la corbeille à la mise en ligne.
- **11** — le délai de perte acceptable pour les pièces (aujourd'hui 24 h).
- **29** — la durée d'une session et le délai d'inactivité, plus courts au
  siège.
- **41** — qui reçoit l'alerte d'exploitation (un ticket GitHub n'envoie
  aucun courrier depuis la plateforme, mais il faut quelqu'un pour le lire).

## Écartés ou rétrogradés à la relecture

- **« Une ligne d'un dossier clôturé se tranche encore »** : rapporté
  majeur, aucun chemin des services n'y mène (un dossier ne se clôt que
  justifié, donc sans ligne non justifiée, et une rectification le fait
  sortir de la clôture). Rétrogradé en invariant non gardé (écart 3).
- **Squasher les migrations** : écarté, les `RunSQL` des déclencheurs
  d'immutabilité ne s'élident pas ; une doctrine les remplace (écart 21).
- **Une nouvelle application tirée d'`expenses`** : écartée ; `expenses`
  reste cohérent depuis la décision 131. Seuls l'import et l'outillage
  changent de place (écart 9).
- **TanStack Query** : écarté, une dépendance de plus pour une personne ;
  un registre de clés maison suffit (écart 38).
- **Sentry, Alertmanager, courrier d'alerte** : écartés tant que la
  décision 88 tient ; l'alerte passe par un ticket (écart 41).
