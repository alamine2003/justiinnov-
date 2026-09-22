# Audit de résilience — JUSTI INNOV

Septembre 2026. **Deux séries.** La première : dix phases d'injection de
pannes sur un banc dédié, seize scénarios, un rapport (§1 à §8). La seconde,
ouverte par ce rapport : huit chantiers d'infrastructure — index et cache,
archivage et reprise, réplique, aiguillage, dépôt de 20 Mo, TLS,
surveillance, deux machines — chacun joué, mesuré, et souvent contredit par
la mesure (§9).

Ce document est le compte rendu complet : ce qui a été éprouvé, ce qui a
cédé, ce qui a tenu, ce qui a été corrigé, ce qui ne l'a pas été et
pourquoi. Les décisions elles-mêmes vivent dans
[`model-de-donnees.md`](model-de-donnees.md) §8, numéros **60 à 77** ; on
les référence ici sans les recopier.

**Tous les chiffres de ce document ont été mesurés.** Aucun n'est estimé.
Quand une mesure manque, c'est écrit. Quand une mesure a contredit ce que
le dépôt affirmait, c'est écrit aussi — c'est arrivé quatre fois.

---

## 0. Le rapport en une page

**Ce que l'audit a établi.** L'architecture était juste pour la charge :
cinquante requêtes par seconde à 6 009 lignes, soit cinquante personnes qui
cliquent en même temps, quand les dix-sept filiales n'en approchent pas.
Ce qui manquait n'étaient pas des briques mais des **bornes** : chaque
attente était infinie, et chaque panne partielle — stockage muet, base
muette — devenait un arrêt total sans reprise. Seize scénarios, onze échecs
ou partiels, dix corrigés, un assumé.

**Ce que la seconde série a ajouté**, et pourquoi chaque ajout a été
justifié par une mesure avant d'exister :

| chantier | mesure qui a tranché | décision |
|---|---|---|
| index de tri | coût plat : 15,59 → 0,018 ms à 600 000 lignes ; **aucun débit gagné aujourd'hui** (63,9 contre 62,7 req/s, bruit) | 72 |
| Redis comme cache, avec filet | 1 478 octets de journal d'écriture **par `GET`** → 0 ; le filet mesuré, sans lui la plateforme serait *moins* sûre | 73 |
| archivage et reprise à un instant donné | une panne à 01:59 perdait la journée ; reprise en **0,6 s**, 3 000 lignes retrouvées | 74 |
| réplique en attente chaude | retard 0,69 ms, promotion 0,11 s, aucune perte sous `SIGKILL` ; `max_slot_wal_keep_size` protège la primaire | 75 |
| aiguillage devant deux machines | service rétabli **4,8 s** après promotion ; **22 s** d'indisponibilité dont 17 d'attente humaine | 76 |
| surveillance des erreurs | trois fuites trouvées **en lisant un événement réel**, aucune visible dans le code | 77 |

**Ce que la mesure a contredit** — le résultat le plus important de la
seconde série, à lire avant le reste :

1. **L'aiguillage ne protège pas du retour d'une ancienne primaire.** Trois
   textes du dépôt affirmaient le contraire. Mesuré : rallumée telle quelle,
   elle reprend le trafic **5,1 s** après son retour, sur une base périmée,
   et 22 requêtes sur 24 y sont allées. Aucune correction technique
   proportionnée n'existe ; la consigne d'exploitation est désormais la
   seule protection, et elle est écrite comme telle (§9.5).
2. **Un dépôt de 20 Mo exigeait une liaison à plus de 70 Ko/s** — alors
   que le délai en cause était justifié, dans son commentaire, par « une
   liaison lente ». Coupé à 301,8 s ; désormais 201 en 341,3 s à 60 Ko/s
   (§9.6).
3. **La même panne de stockage donnait un 503 clair en sortie et un 500
   opaque en entrée** (§9.7).
4. **Une configuration de confidentialité ne se relit pas, elle se mesure**
   : `send_default_pii=False` laissait partir le compte, l'adresse et les
   données validées (§9.9).

**Ce qui reste hors d'atteinte du banc**, et se joue sur le serveur : Let's
Encrypt lui-même (deux obstacles, dont un de topologie), MinIO lui-même,
deux machines réelles. Pour chacun, l'outil qui rend la vérification
possible là-bas est livré : `verifier_tls.sh`, `chronometrer_bascule.sh`,
et le mode opératoire dans `deploy/README.md` (§10).

**En chiffres** : 21 commits, 154 tests ajoutés — chacun vérifié rouge sur
le code d'avant —, suite complète à **1 233 tests**, verte ; 18 décisions
consignées (60 à 77) ; 4 affirmations du dépôt démenties et corrigées.

---

# Première partie — dix phases sur banc

## 1. Méthode et garde-fous

Boucle imposée, tenue pour chaque défaut :

> hypothèse → injection → observation → mesure → **cause racine** →
> correction → nouveau test → validation

Règles respectées sans exception :

- **aucun test destructif sur une production réelle.** Tout s'est passé sur
  un banc local : PostgreSQL 16 sur un port dédié, base `justi_chaos`
  jetable, gunicorn sur 127.0.0.1:8009, serveur de courrier factice ;
- **chaque panne injectée est reproductible, mesurable et réversible.** Les
  injections passent par des outils écrits pour l'occasion — mandataire TCP
  à latence réglable, trou noir TCP, `SIGSTOP`/`SIGCONT`, occupation de
  connexions — et jamais par une modification du code de l'application ;
- **aucune donnée importante supprimée.** La base du banc a été remplie de
  données jetables (404 dossiers, 6 009 lignes, 60 comptes) ;
- **un correctif s'accompagne du test qui l'aurait attrapé**, et ce test est
  vérifié **rouge sur le code d'avant** avant d'être retenu.

Volume du banc : **6 009 lignes de dépense**, soit environ dix ans de
l'activité attendue des dix-sept filiales. Les mesures de capacité valent
donc pour une plateforme déjà vieille, pas pour une base vide.

---

## 2. Architecture relevée

```
                    Internet
                       │
                  ┌────▼─────┐
                  │  Caddy   │  TLS, redirection
                  └────┬─────┘
                       │
                  ┌────▼─────┐
                  │  nginx   │  sert React, mandate /api/
                  │          │  limit_req 40 r/s par IP, rafale 80
                  └────┬─────┘
                       │
              ┌────────▼─────────┐
              │    gunicorn      │  gthread, 2 processus × 4 fils
              │   (Django/DRF)   │  → 8 requêtes en parallèle
              └───┬──────────┬───┘
                  │          │
         ┌────────▼───┐  ┌───▼────────┐
         │ PostgreSQL │  │   MinIO    │  justificatifs
         │     16     │  └────────────┘
         └─────┬──────┘
               │            ┌──────────────┐
               ├────────────┤ ordonnanceur │ APScheduler, 6 tâches
               │            └──────────────┘
               │            ┌──────────────┐
               └────────────┤ sauvegardes  │ pg_dump + miroir des pièces
                            └──────────────┘
```

**Ce que PostgreSQL porte, à lui seul** — c'est le fait structurant de
cette architecture, et il explique la moitié des constats de ce rapport :

| rôle | mise en œuvre |
|---|---|
| base métier | tables `expenses_*`, `budget_*`, `accounts_*` |
| **cache** | `DatabaseCache`, table `django_cache` |
| **file d'attente** | `Notification.emailed_at`, `FichierASupprimer` |
| **compteurs de limitation de débit** | `django_cache` |
| verrous métier | `select_for_update` |

Il n'y a **ni Redis, ni Celery, ni courtier de messages**. Ce n'est pas un
manque : pour une charge de cette taille, chaque brique en moins est une
panne en moins à prévoir. Mais cela concentre le risque, et la limitation de
débit paie ce choix en écriture (§5).

---

## 3. Points de défaillance unique

Tout tourne sur **une seule machine**. Les points ci-dessous se lisent avec
cette réserve : une panne de l'hôte les emporte tous.

| composant | conséquence de sa perte | état après l'audit |
|---|---|---|
| **PostgreSQL** | arrêt total — base, cache, files, verrous | perte **bornée** : 503 + `Retry-After` en 3,0 s (déc. 70) |
| **MinIO** | dépôt et téléchargement de pièces | perte **bornée** : 503 en 31–34 s au téléchargement, **et désormais au dépôt aussi** (§10) ; reste de l'API intact (déc. 60) |
| **gunicorn** | API | worker abattu : perte des seules requêtes en vol, renaissance en 0,39 s |
| **ordonnanceur** | relances d'e-mails, alertes, contrôle des sauvegardes | **dégradation seulement** : les files sont des tables, le travail attend |
| **nginx / Caddy** | accès | bascule à deux machines jouée : 22,0 s d'indisponibilité, dont 17,1 s d'attente humaine ; retour d'une ancienne primaire **non protégé** (§10) |

La conclusion qui compte : **aucun de ces points n'était borné avant
l'audit**, et deux d'entre eux — stockage et base — transformaient une panne
partielle en **arrêt total et sans reprise** de l'API. C'est le fil rouge de
tout ce qui suit.

---

## 4. Résultat par scénario

| # | scénario | résultat | ce qu'il a établi |
|---|---|---|---|
| 1 | SIGKILL en pleine écriture | **PARTIEL** | Données intactes, mais la livraison coupait les dépôts en cours |
| 2 | Saturation des connexions | **RÉUSSITE** | Borne structurelle, plafond non choisi |
| 3 | Base injoignable (arrêt net) | **ÉCHEC** | 500 au lieu de 503, aucun journal, page HTML |
| 4 | Base lente (latence injectée) | **RÉUSSITE** | Dégradation régulière, sans falaise |
| 5 | Base muette (trou noir) | **ÉCHEC** | Toute l'API pendue > 90 s |
| 6 | Base figée (`SIGSTOP`) | **ÉCHEC — non corrigé** | Toujours > 95 s ; aucun réglage ne peut y répondre (§10) |
| 7 | Stockage muet | **ÉCHEC** | Toute l'API muette, sans reprise |
| 8 | Serveur de courrier mort | **PARTIEL** | Mécanisme sain, abandon final silencieux |
| 9 | Deux ordonnanceurs simultanés | **RÉUSSITE** | 60 envoyés, 60 reçus, **0 doublon** |
| 10 | Amplification pendant une panne | **PARTIEL** | 5,7× de débit, et 24 Mo de journaux en 7 s |
| 11 | Volume (9 → 6 009 lignes) | **RÉUSSITE** | Aucun N+1 ; le coût vient d'ailleurs (§5) |
| 12 | `EXPLAIN` sur `/api/expenses/` | **ÉCHEC** | Planification 91 ms pour 43 ms d'exécution |
| 13 | Limite de connexion sous concurrence | **ÉCHEC** | 5 annoncées, 13 passées |
| 14 | Purge du cache | **ÉCHEC** | 400 comptes actifs effaçaient l'anti-bourrage |
| 15 | Invariants métier après chaos | **RÉUSSITE** | 15 invariants, tenus (réserve en §10) |
| 16 | Pannes combinées (Phase 3) | **RÉUSSITE** | **Aucune amplification** entre pannes |

Onze échecs ou partiels, dix corrigés, **un assumé** (scénario 6).

---

## 5. Goulots mesurés

### 5.1 La planification, pas l'exécution

Le résultat le plus contre-intuitif de l'audit. Sur `/api/expenses/`, à
6 009 lignes :

```
Planning Time: 107.8 ms      ← le planificateur
Execution Time: 46.1 ms      ← la requête elle-même
```

Le coût suit le **nombre de tables jointes**, jamais le nombre de lignes :

| relations jointes | planification | exécution |
|---|---|---|
| 1 | 0,1 ms | 4,5 ms |
| 3 | 0,6 ms | 13,7 ms |
| 9 | 59,6 ms | 35,2 ms |
| **14 (livré)** | **91,2 ms** | 43,0 ms |

Et rien ne l'amortissait : Django ne prépare aucune requête
(`prepare_threshold` vaut `None`), donc dix appels d'affilée sur la même
connexion coûtent dix fois 133 ms. Lire **une seule ligne** se payait au
même prix qu'une page.

Ce n'était ni `geqo` (le désactiver ne change rien), ni un index manquant,
ni les deux `EXISTS` de `with_rectification` (1,4 ms). Correction :
préchargement plutôt que jointure (déc. 67).

### 5.2 Les allers-retours, quand le réseau se dégrade

Le correctif précédent échange 9 allers-retours contre 91 ms de
planification. Il a donc un point de bascule, mesuré :

| aller-retour | préchargé | joint |
|---|---|---|
| 0,6 ms | **58 ms** | 207 ms |
| 11,8 ms | **266 ms** | 287 ms |
| 21,4 ms | 445 ms | **380 ms** |
| 51,6 ms | 1016 ms | **680 ms** |

Croisement à **≈ 10 ms**, que l'arithmétique prédit : 9 allers-retours
contre 91 ms fixes. La pile livrée est à **0,09 ms** — deux ordres de
grandeur en dessous. Une base hébergée ailleurs ne le serait pas ; c'est
écrit à côté de `DATABASE_URL`.

### 5.3 La limitation de débit écrit à chaque lecture

Le compteur est une liste d'horodatages relue et réécrite à chaque requête,
dans PostgreSQL :

| historique du compte | journal d'écriture par `GET` |
|---|---|
| vide | 780 o |
| 100 entrées | 1 489 o |
| 1 000 entrées | 4 250 o |

La table du cache pèse **1 576 ko pour 57 ko de contenu utile**. C'est le
prix de l'algorithme de DRF, assumé pour la limite générale (§7).

### 5.4 Les fils, pas le processeur

Le serveur ouvre **exactement `workers × threads`** connexions — mesuré : 8
à 2×4, jamais davantage. La borne est structurelle ; il n'y a pas de
réserve qui grossit, et donc **aucun besoin d'un gestionnaire de
connexions**.

Et depuis le préchargement, quatre cœurs saturés ne changent **rien** :
50,8 req/s contre 49,6 au repos. L'écran attend le réseau, il ne calcule
plus.

---

## 6. Incidents critiques et causes racines

### 6.1 Un stockage muet emportait toute l'API — **CRITIQUE**

**Observation.** Huit téléchargements simultanés vers un stockage qui
accepte la connexion sans jamais répondre ont tenu les huit fils de gunicorn
**plus de 140 secondes**, et les écrans qui ne touchent aucun fichier
répondaient `000` après 30 s d'attente. Sans reprise, et sans une ligne de
journal.

**Cause racine.** Aucun `client_config` sur le client S3 : botocore attend
60 s par tentative et recommence jusqu'à cinq fois. Le `--timeout 120` de
gunicorn ne rattrape rien — en mode `gthread`, il surveille la boucle du
worker, pas ses fils de requête.

**Après.** 503 en 31–34 s pour le téléchargement, et le reste de l'API à
**0,02 s dès t+13 s**. Décision 60.

### 6.2 En production, une panne ne laissait aucune trace — **IMPORTANT**

**Observation.** Pendant une coupure de la base, **6 307 erreurs 500 ont
produit zéro ligne de journal**. Restait le code d'état dans le journal
d'accès, et rien pour dire pourquoi.

**Cause racine.** Django n'a pas de configuration de journalisation
utilisable hors mode debug : son gestionnaire console porte le filtre
`RequireDebugTrue`, et celui par courriel n'écrit nulle part sans `ADMINS`
— qui était vide.

**Après.** Chaque ligne porte `requete=`, `compte=`, `ip=`, et
l'identifiant part au client en en-tête `X-Requete-Id` : la personne qui
signale un incident peut le citer. Décision 61.

### 6.3 Le correctif précédent a créé une panne pire — **IMPORTANT**

À signaler, parce que c'est une erreur que j'ai commise et trouvée en
remesurant : une fois la journalisation rétablie, une coupure de base
écrivait **24 Mo de traces en sept secondes** (7,8 ko par erreur, et le
débit *monte* pendant une panne : 53 → 307 req/s). Docker retenant 100 Mo
par service, **une demi-minute de panne effaçait tout l'historique**, y
compris les lignes d'avant la panne.

Le même test produit désormais **17,8 ko et seize lignes**. Décision 63.

### 6.4 Chaque livraison coupait les dépôts en cours — **IMPORTANT**

**Observation.** Six `SIGKILL` au cœur d'une transaction (à 8,0 / 8,2 / 8,6
/ 9,0 / 9,2 / 9,4 s d'une opération de 9,5 s) laissent l'état **identique** :
aucun fichier orphelin, aucune ligne orpheline, aucune transaction ouverte,
aucun verrou resté. Les workers renaissent en 0,39 s. Le circuit est
atomique, c'est établi.

**Mais** la vidange de gunicorn a été mesurée à **11,07 s**, alors que
Compose n'accordait que les **10 s** de son défaut. Une seconde de trop : à
chaque livraison, quelqu'un perdait la pièce qu'il déposait. Aucune donnée
corrompue — le travail d'une personne, si. Décision 64.

### 6.5 La limite anti-bourrage fuyait avec le parallélisme — **IMPORTANT**

**Observation.** Cinq essais autorisés par compte et par minute :

| tentatives | essais non bloqués |
|---|---|
| douze, une par une | **5** — exact |
| quarante simultanées, 4 fils | 7 |
| quarante simultanées, 8 fils | 11 |
| quarante simultanées, 16 fils | **13** |

**Cause racine.** Le compteur de DRF lit l'historique, y ajoute l'instant
courant, réécrit le tout — sans verrou. La dernière écriture efface
l'autre.

**Conséquence de gouvernance**, plus grave que le chiffre : **relever
`GUNICORN_THREADS` affaiblissait la protection**, et rien ne le disait.
Après correction : **exactement 5**, trois fois de suite. Décision 68.

### 6.6 La croissance de la plateforme effaçait cette même protection — **IMPORTANT**

**Observation.** `DatabaseCache` purge au-delà de `MAX_ENTRIES` — 300 par
défaut — et supprime **par ordre alphabétique de clé, pas par ancienneté**.
Les compteurs s'appellent `throttle_login_<adresse>` : ils se classent parmi
les plus bas.

| comptes actifs dans l'heure | compteur anti-bourrage |
|---|---|
| 250 | encore là |
| **400** | **effacé** |

Aucun attaquant n'est nécessaire. Décision 69.

### 6.7 Ce que le journal annonçait était faux — **AMÉLIORATION**

Le journal écrivait « N e-mail(s) à reprendre » à chaque échec, puis, une
fois `ESSAIS_MAX` atteint, les lignes cessaient d'être réclamées **sans un
mot**. Soixante notifications abandonnées en silence sur le banc, avec un
exploitant qui aurait cru la reprise en cours. Décision 65.

---

## 7. Changements, classés

### CRITIQUE

| changement | preuve |
|---|---|
| Délais bornés sur le client S3 (déc. 60) | arrêt total > 140 s → 503 en 31–34 s |
| Délais bornés sur la base, des deux côtés (déc. 70) | arrêt total > 90 s → 503 en 3,0 s |

### IMPORTANT

| changement | preuve |
|---|---|
| Journalisation en production (déc. 61) | 6 307 erreurs → 0 ligne, puis trace complète nommée |
| 503 + `Retry-After` + JSON partout (déc. 62) | `/api/health/` 503 et `/api/dossiers/` 500 pour la même panne |
| Débit des journaux borné (déc. 63) | 24 Mo/7 s → 17,8 ko |
| `stop_grace_period` déclaré (déc. 64) | vidange 11,07 s contre 10 s accordées |
| Comptage exact des tentatives (déc. 68) | 13 passées sur 5 autorisées → 5 |
| Plafond de purge du cache (déc. 69) | 400 comptes actifs effaçaient la protection |
| Préchargement des relations (déc. 67) | 22,4 → 49,1 req/s, P95 470 → 286 ms |

### AMÉLIORATION

| changement | preuve |
|---|---|
| Plafond de connexions choisi (déc. 66) | 100 par défaut contre 1 Go de mémoire ; 1,9–2,4 Mo par connexion |
| Abandons d'e-mails signalés (déc. 65) | 60 abandons silencieux, dernière ligne trompeuse |

### NON NÉCESSAIRE — écarté après mesure

C'est la partie du rapport qu'il faut lire avec le plus d'attention : ce
qu'on n'a **pas** fait, et pourquoi.

| envisagé | écarté parce que |
|---|---|
| **Redis / Celery** | Les files sont des tables et elles tiennent : 60 envoyés, 60 reçus, 0 doublon, **y compris avec deux ordonnanceurs simultanés**. Une brique en plus serait une panne en plus |
| **pgbouncer** | Le serveur ouvre exactement `workers × threads` connexions. La borne est structurelle : il n'y a pas le problème que résoudrait un gestionnaire de connexions |
| **Disjoncteur (circuit breaker)** | L'amplification mesurée (5,7×) vient de clients qui n'honorent aucun `Retry-After` ; l'interface n'a pas de logique de reprise et nginx borne déjà à 40 r/s par IP. Le vrai danger était le déluge de journaux, corrigé |
| **`join_collapse_limit = 1`** | Ramenait la planification de 110 à 6,1 ms — mais **dégrade `/api/budgets/` de 9,6 à 22,7 ms**. Un réglage global rend le planificateur aveugle partout, y compris sur ce qu'on n'a pas mesuré |
| **Verrouiller la limite générale (2000/h)** | Elle ne défend rien — elle borne un client emballé. La sérialiser ferait attendre chaque requête d'un compte derrière la précédente, pour aucun gain |
| **Remplacer l'algorithme de limitation** | 1,5 ko de journal d'écriture par `GET` : réel, mesuré, et moins coûteux que le risque de réécrire un composant éprouvé sur le chemin de **chaque** requête |
| **Sonde de santé interrogeant la base pour l'ordonnanceur** | Ferait redémarrer l'ordonnanceur en boucle au moindre hoquet de la base. La surveillance passe par le journal, désormais lisible |
| **File de rebut pour les e-mails** | Rien n'est perdu : la notification reste lisible dans l'application. Une alerte par courriel sur une panne de courriel serait circulaire |

---

## 8. Capacité mesurée

À **6 009 lignes**, 2 processus × 4 fils, sur 4 cœurs :

| condition | débit | P50 | P95 | erreurs |
|---|---|---|---|---|
| `/api/expenses/`, 8 clients, avant préchargement | 22,4 req/s | 357 ms | 470 ms | 0 |
| `/api/expenses/`, 8 clients, après | **49,1 req/s** | 150 ms | 286 ms | 0 |
| `/api/expenses/`, 16 clients | 50,1 req/s | 287 ms | 560 ms | 0 |
| 16 clients + latence base 5 ms | 27,1 req/s | 584 ms | 727 ms | 0 |
| 16 clients + latence base 25 ms | 6,9 req/s | 2 157 ms | 3 101 ms | 0 |
| 16 clients + latence base 100 ms | 1,4 req/s | 8 166 ms | 12 546 ms | 0 |
| 16 clients + **4 cœurs saturés** | 50,8 req/s | 305 ms | 437 ms | 0 |

Connexions à la base : **8 sur 50** au réglage livré ; budget complet de la
pile **25 sur 50**.

**Lecture pour la direction.** Cinquante requêtes par seconde, c'est
l'ordre de grandeur de **cinquante personnes qui cliquent en même temps**.
Les dix-sept filiales n'approchent pas ce chiffre. La plateforme n'est pas
limitée par sa capacité ; elle l'est par ce qui se passe quand un élément
tombe — ce que cet audit a corrigé.

---

# Seconde partie — après le rapport des dix phases

## 9. Huit chantiers, joués et mesurés

Le rapport des dix phases concluait qu'aucune brique ne manquait. Les
chantiers suivants ont été demandés ensuite, un par un ; chacun est entré
dans le dépôt seulement après mesure, et trois d'entre eux ont fini par
contredire ce que le dépôt affirmait. L'ordre est chronologique.

### 9.1 Index de tri, Redis comme cache, infrastructure de la base

Décisions 72 et 73 ; `docs/infra-base-de-donnees.md` pour le
dimensionnement. Deux résultats, dont un négatif qu'il faut garder :

| mesure | avant | après |
|---|---|---|
| tri d'une page de 25 lignes, 6 000 lignes en table | 0,95 ms | 0,015 ms |
| à 60 000 lignes | 3,37 ms | 0,016 ms |
| à 600 000 lignes | 15,59 ms | 0,018 ms |
| prix à l'écriture | — | +11 %, soit 2 µs par ligne |
| débit sous charge à 6 009 lignes | 62,7 req/s | 63,9 req/s — **dans le bruit** |

L'index `depense_tri_liste` n'achète **pas** de débit aujourd'hui : la
requête SQL pèse 3 ms sur 250. Il achète la tenue dans dix ans, et c'est
pour cela qu'il est là. Un second index candidat a été mesuré puis écarté —
jamais choisi par le planificateur, payé à chaque écriture —, et aucun n'a
été ajouté aux tables qui tiennent sur une page.

Redis remplace `DatabaseCache` pour une raison mesurée, pas pour la vitesse
(62,0 contre 62,6 req/s) : la limitation de débit écrivait **1 478 octets de
journal de transaction par `GET`** et quatre requêtes sur `django_cache` par
appel, désormais zéro — ce qui referme une exception non documentée à la
règle « une requête `GET` n'écrit rien ». Le filet (`CacheAvecSecours`) n'est
pas optionnel : un cache sans repli ferait de chaque requête une 500 quand
Redis tombe, et la plateforme serait *moins* sûre qu'avant. Le repli est
mesuré : écriture et lecture passent, une ligne de journal par minute.

### 9.2 Archivage des journaux et reprise à un instant donné

Décision 74. La chaîne de sauvegarde était sérieuse — dump quotidien
chiffré, copie mensuelle, miroir hors machine vérifié — mais sa seule
granularité de reprise était le dump de 02:00 : **une panne de disque à
01:59 perdait toute la journée**, pour une application dont la raison d'être
est de savoir où est la preuve.

Éprouvé de bout en bout sur un banc de 72 Mo : sauvegarde physique en
**3,0 s**, reprise à l'instant demandé en **0,6 s**, les 3 000 lignes
effacées par erreur retrouvées et l'erreur absente. Le mode de panne à
connaître : tant que l'archivage échoue, Postgres garde ses segments dans
`pg_wal` jusqu'à remplir le disque — il préfère s'arrêter que perdre.
`verifier_sauvegardes` le surveille. Ce mécanisme a d'ailleurs rattrapé le
banc lui-même, deux fois : un emplacement de réplication orphelin, puis un
archivage relancé sans destination — chaque fois vu par la suite de tests
avant d'être compris.

### 9.3 Réplique en attente chaude

Décision 75. Deux grappes locales, réplication par flux : retard **0 octet /
0,69 ms**, copie initiale de 15 Mo en **0,5 s**, promotion en **0,11 s**,
et **aucune perte** après un `SIGKILL` de la primaire. Le cœur de la décision
est la borne `max_slot_wal_keep_size` : sans elle, une réplique absente fait
grandir `pg_wal` jusqu'à remplir le disque de la primaire — mesuré ; avec
elle, l'emplacement passe à `lost`, la primaire continue, et c'est la
réplique qu'on refait. Réplication asynchrone, assumée : en synchrone, une
réplique absente bloquerait toute la plateforme.

### 9.4 L'aiguillage : ce que l'analyse des `Caddyfile` a trouvé

`email {$ACME_EMAIL}` n'était pas entre guillemets. Une variable **posée
vide** fait disparaître le placeholder : la directive se retrouve sans
argument et **Caddy refuse de démarrer**, sur une erreur qui ne nomme que
`email`. Le défaut `{$NOM:valeur}` n'y change rien — mesuré : il ne joue que
si la variable est *absente*, jamais si elle est posée vide.

Le cas n'était pas atteignable par la commande documentée, et il faut le dire
aussi nettement : `docker compose config` refuse un `ACME_EMAIL` vide, parce
que le `:?` de `docker-compose.prod.yml` s'applique avant la surcharge. Mais
`docker-compose.derriere-balanceur.yml` posait `${ACME_EMAIL:-}`, c'est-à-dire
une ligne qui **annonçait une souplesse qu'elle ne pouvait pas tenir** :
l'exploitant reste obligé de renseigner une adresse dont cette machine ne se
sert pas, et le jour où quelqu'un relâcherait `prod.yml` en s'y fiant,
l'entrée publique ne démarrerait plus.

Corrigé en trois points : le placeholder est entre guillemets dans les deux
fichiers (renseigné, il part à ACME à l'identique — vérifié sur la
configuration produite) ; la ligne trompeuse est remplacée par ce qu'elle
aurait dû dire ; et `core/tests/test_caddy.py` vérifie la règle générale —
*un placeholder sans guillemets n'est acceptable que si Compose garantit une
valeur non vide*. Ce test est rouge sur le code d'avant.

Pourquoi rien ne l'avait vu : l'intégration continue renseigne une adresse
factice (`ci@example.invalid`) alors qu'elle ne termine pas TLS. Le seul
chemin qui aurait révélé le défaut était celui que personne ne joue.

---

### 9.5 La bascule jouée — **IMPORTANT** : la garantie qui n'existait pas

Banc : PostgreSQL 16 primaire (`m1`) et réplique en flux (`m2`, montée avec
les options exactes de `preparer_replique.sh`), la vraie application Django
sur chacune, `balanceur/Caddyfile` non modifié devant. Une sonde interroge
l'aiguillage toutes les deux secondes ; les décisions de Caddy sont lues dans
son propre journal.

| moment | mesure |
|---|---|
| perte de `m1` (application et base, arrêt immédiat) | première erreur vue par la sonde : **immédiate** (502) |
| Caddy constate la perte | **1,6 s** après l'arrêt |
| réplique non promue, pendant 17 s | **0 requête** servie par `m2` — le contrôle d'écriture fait son travail |
| promotion + démarrage de l'application sur `m2` | service rétabli **4,8 s** plus tard, soit un intervalle de contrôle |
| indisponibilité totale | **22,0 s**, dont 17,1 s d'attente de la décision humaine de promouvoir |

Ce qui marche, marche bien : aucune requête n'a été envoyée à une base en
lecture seule, et l'aiguillage a suivi la nouvelle primaire en moins de cinq
secondes, sans toucher au DNS. C'est exactement ce que la décision 76
promettait.

**Ce qui ne marche pas est plus grave que ce que le dépôt écrivait.** Le
`Caddyfile`, la docstring de `HealthView` et l'en-tête de
`core/tests/test_balanceur.py` affirmaient tous les trois qu'une ancienne
primaire redémarrée après une bascule « se déclare indisponible » et que
« personne n'y retourne ». C'est faux, et la mesure est nette : redémarrée
telle quelle, elle n'est pas en récupération, elle accepte les écritures,
`/api/health/` y répond **200 `writable:true`** — en toute sincérité —, et
`lb_policy first`, qui préfère toujours la première machine, lui **rend la
préférence**.

| moment | mesure |
|---|---|
| retour de l'ancienne primaire (base + application) | — |
| Caddy la déclare saine | **5,0 s** |
| première requête servie par la base périmée | **5,1 s** |
| trafic des 24 requêtes suivantes | **22 sur la périmée**, 2 sur la vraie primaire |
| divergence au même instant | 1 000 lignes contre 1 500 ; timeline 1 contre 2 |

**Cause racine.** Le contrôle répond à « puis-je écrire ? », pas à « suis-je
la primaire d'aujourd'hui ? ». Une base déposée répond oui aux deux
questions qu'on sait lui poser. Aucun signal local ne les distingue : la
timeline (1 contre 2) le ferait, mais une machine ne connaît que la sienne,
et le fichier `.history` qui l'annonce est écrit dans l'archive de **l'autre**
machine — en production, un volume local, pas un dépôt partagé. Et
l'aiguillage aggrave le cas au lieu de le couvrir : sans lui, il faut qu'une
personne rebascule le DNS ; avec lui, le retour est automatique.

**Correction.** Aucune n'est technique, et c'est le résultat le plus
important de cette épreuve. Départager deux bases demanderait qu'une
troisième instance arbitre — Patroni, repmgr, etcd : une dépendance, un
quorum, une machine de plus à tenir, pour un dispositif qui bascule à la
main une fois tous les combien d'années. Ce n'est pas justifié ici, et
inventer un demi-mécanisme non éprouvé serait pire que la consigne. Donc :

1. les trois endroits qui promettaient la protection disent maintenant ce
   qui est mesuré, chiffres compris — un exploitant qui croit la machine
   protégée ne prendra pas la précaution qui, elle, protège ;
2. `promouvoir_replique.sh` porte l'avertissement en toutes lettres, avec la
   commande à passer **avant** que l'ancienne machine ne redémarre seule
   (`docker compose down` à distance), car « restart: unless-stopped » la
   rallumera au prochain démarrage de l'hôte sans demander l'avis de
   personne.

**Une piste écartée après mesure**, pour mémoire : ma première passe montrait
un battement — machines déclarées mortes puis vivantes toutes les trente
secondes. C'était ma sonde à 5 req/s qui saturait la limite de débit du point
de santé (60/min par adresse), et les contrôles de Caddy, partageant le même
compteur, recevaient des 429 ; toute réponse différente de 200 vaut « machine
morte ». Rejoué à 0,5 req/s : plus un seul 429. Ce n'était donc pas un défaut
du système — mais la mécanique est réelle, et mérite d'être connue : **une
réponse 429 sur `/api/health/` fait déclarer une machine saine hors service
pendant 30 s** (`fail_duration`). Elle ne se déclenche que si l'adresse vue
par Django dépasse 60 requêtes par minute, ce qui suppose un
`DJANGO_NUM_PROXIES` faux — précisément ce que `test_balanceur.py` vérifie
déjà.

### 9.6 Le dépôt d'une pièce de 20 Mo, et la liaison lente

Banc : les quatre étages de la production, chacun dans sa configuration du
dépôt, sans retouche — aiguillage Caddy, Caddy de la machine, nginx (le
gabarit `frontend/nginx.conf` rendu par son propre script d'entrée), puis
gunicorn et Django. nginx tourne dans son espace de noms réseau, comme un
conteneur, pour que le port 80 de chacun soit vraiment le sien. Les pièces
sont de vrais PDF ; l'empreinte SHA-256 de la source est comparée à celle du
fichier stocké.

| essai | résultat |
|---|---|
| 20 Mo, liaison locale | **201 Créé en 0,39 s**, fichier stocké **identique octet pour octet** |
| 20 Mo à 200 Ko/s | **201 Créé en 102,4 s** |
| 20 Mo à 60 Ko/s | **coupé à 301,8 s** après 18,5 Mo → 502, **dépôt perdu** |
| 21 Mo (au-dessus de MAX_PROOF_SIZE) | 400 : « Fichier trop volumineux (maximum 20 Mo). » |
| le même fichier deux fois | 400 : « Ce fichier est déjà rattaché à ce dossier (doublon). » — la contrainte de la décision 45 tient de bout en bout |

**Le troisième essai est le défaut, et il vise exactement les filiales.**
nginx met le corps de la requête en fichier temporaire et **ne répond qu'une
fois le dépôt entièrement reçu** ; le temps de téléversement tombe donc dans
le `read_timeout` de l'aiguillage, qui est un délai *total*. À 300 s, une
pièce de 20 Mo exigeait une liaison à plus de ~70 Ko/s (560 kbit/s) — et le
commentaire du `Caddyfile` invoquait pourtant « le dépôt d'une pièce de 20 Mo
sur une liaison lente » pour justifier cette valeur. Le délai ne tenait pas
ce que son commentaire promettait.

**Corrigé** : `read_timeout 900s`, ce qui descend le plancher à ~23 Ko/s
(185 kbit/s). Rejoué à 60 Ko/s : **201 Créé en 341,3 s**, fichier intact. Ce
que cela coûte, et c'est assumé : une connexion enlisée tient jusqu'à quinze
minutes, Caddy n'offrant pas de délai « par lecture » comme nginx. Un test
lie désormais les deux nombres qui doivent s'accorder — `MAX_PROOF_SIZE` et
`read_timeout` — pour qu'une pièce plus grosse, un jour, rouvre la question.

**Une correction que j'ai faite puis retirée, faute d'avoir mesuré avant.**
Un fichier de 26 Mo, au-dessus des 25 Mo des mandataires, est refusé par
nginx sur `Content-Length` — donc immédiatement —, mais sa réponse 413 est
parfois détruite en route : nginx ferme la connexion pendant que Caddy lui
écrit encore, et le client reçoit un 502 à corps vide. J'ai voulu relever la
borne de nginx pour que Caddy rende le 413 lui-même. Mesuré : c'est **pire**.
Caddy ne découvre le dépassement qu'en lisant, donc le client envoie 25 Mo
pour rien avant d'être coupé, et n'obtient souvent aucun statut exploitable.
Rétabli. Le comportement livré, mesuré sur trois essais, est rapide et
imparfait : refus en ~2 ms après ~2 Mo envoyés, statut 413 ou 502 selon la
course. Cela ne touche pas les utilisateurs : l'interface refuse le fichier
avant l'envoi, sur une borne que le serveur lui donne
(`configuration.justificatifs.taille_max_mo`). Rendre ce statut déterministe
demanderait de comparer `Content-Length` dans l'aiguillage, soit une
troisième copie de la borne à tenir en accord — non justifié pour un cas que
seuls les clients hors interface rencontrent.

### 9.7 Le stockage objet — **IMPORTANT** : la même panne, deux réponses

Même banc, avec cette fois un serveur S3 à la place du disque local. **Ce
n'est pas MinIO** : son binaire n'est pas récupérable depuis ce banc, et
aucun paquet ne le fournit. Ce qui est donc éprouvé, c'est tout le chemin de
l'application — `django-storages`, `botocore`, le découpage en parties, les
délais, la mémoire — et non le comportement propre de MinIO. Les durées
tiennent à l'implémentation d'en face ; les conclusions de code, non.

| essai | résultat |
|---|---|
| 20 Mo déposés | **201 en 1,05 s** (0,39 s sur disque local), objet **identique octet pour octet** |
| 20 Mo téléchargés | **200 en 0,51 s**, fichier identique |
| huit dépôts de 20 Mo simultanés | **8 × 201** en 2,0 à 4,4 s, neuf objets tous conformes |
| mémoire des workers au pic | **487,5 Mo** cumulés, contre `mem_limit: 768m` — **+161,6 Mo** pour les huit dépôts |
| forme de l'envoi | **trois parties de 8 Mo**, en parallèle (découpage par défaut de boto3) |

La mémoire ne redescend pas après coup : elle atteint un palier et y reste.
C'est ce palier qui compte face à la limite du conteneur, et il laisse
280 Mo de marge à huit dépôts simultanés de 20 Mo.

**Le défaut est ailleurs, et il est dans le code.** Avec un stockage bridé,
un dépôt de 20 Mo échouait en **500 « Erreur interne du serveur »**. Or le
*téléchargement* traduit depuis longtemps la même panne en **503** clair
— « Le stockage des justificatifs ne répond pas : réessayez dans un
instant. » (décision 60, `ProofViewSet.download`). Le *dépôt* ne traduisait
rien : `PANNES_DE_BASE` ne couvre que `OperationalError` et
`InterfaceError`, donc la base, et les exceptions botocore remontaient
jusqu'au gestionnaire 500. La même panne donnait une réponse claire en
sortie et une réponse opaque en entrée — un 500 n'invite à aucune reprise,
alors que rien n'est perdu et que réessayer suffit.

**Corrigé** : `ProofViewSet.create` traduit les pannes du client S3
(`BotoCoreError`, `ClientError`) en `StockageIndisponible`, dans le bloc qui
nettoie déjà les fichiers orphelins. Rejoué sur la chaîne complète :
**503 en 16,8 s** avec le message traduit, une seule ligne de journal, aucun
objet orphelin ni envoi en plusieurs parties resté ouvert.

`OSError` est volontairement **hors** de cette famille, bien qu'elle couvre
le disque plein : un test existant la lève pour simuler une trace d'audit
impossible et exige qu'elle **remonte**. Une trace impossible n'est pas une
panne de stockage, et l'habiller en « réessayez » laisserait croire qu'il ne
s'est rien passé. Le premier jet l'incluait ; c'est ce test qui l'a arrêté.

### 9.8 TLS : l'émission éprouvée contre une autorité locale

Le `Caddyfile` de production a demandé un certificat par le vrai circuit
ACME — compte, commande, défi HTTP-01, installation — à une **autorité
locale** tenue par un second Caddy. Ce n'est pas Let's Encrypt : le protocole
et les étapes sont les mêmes, mais ni ses quotas, ni ses enregistrements CAA,
ni le DNS public ne sont éprouvés. Deux lignes ont été ajoutées à une copie du
fichier pour viser cette autorité ; le reste est celui du dépôt.

| vérification | résultat |
|---|---|
| émission | **certificat obtenu**, SAN `justi.banc.test`, chaîne vérifiée |
| protocole | **TLS 1.3**, `TLS_AES_128_GCM_SHA256` |
| redirection depuis le clair | **308** vers `https://` |
| HSTS | `max-age=31536000; includeSubDomains; preload`, **une seule source** |
| `/api/health/` en TLS | **200** |
| dépôt de 20 Mo en TLS | **201 en 0,26 s**, empreinte identique |

Django ne boucle pas malgré `DJANGO_SECURE_SSL_REDIRECT=1` : le
`X-Forwarded-Proto` posé par Caddy et transmis par nginx est lu, comme la
décision le prévoyait. C'était la crainte écrite dans les commentaires ; elle
est levée.

**Un défaut mineur, mesuré au passage** : quatre en-têtes de sécurité sont
servis **en double** sur une réponse d'API — `X-Frame-Options`,
`X-Content-Type-Options` et `Referrer-Policy` viennent de Django *et* de
nginx ; `Permissions-Policy` de nginx *et* de Caddy. HSTS et la politique de
sécurité du contenu, elles, n'ont qu'une source — c'est justement celle dont
le `Caddyfile` se préoccupait. Les valeurs sont identiques, donc sans effet
pratique aujourd'hui ; mais un `X-Frame-Options` en double a déjà été motif,
chez certains navigateurs, à ignorer l'en-tête. Noté, non corrigé : choisir
la source unique de chacun demande de décider ce qui protège les réponses que
Django ne sert pas (les fichiers statiques), et cela se décide.

### 9.8 bis Let's Encrypt lui-même : pourquoi pas d'ici

Demandé deux fois, tenté pour de bon la seconde. **Deux obstacles
indépendants, mesurés et non supposés** :

1. la politique de sortie de l'environnement refuse les deux points d'entrée
   ACME — `acme-staging-v02` et `acme-v02.api.letsencrypt.org` répondent 403
   au `CONNECT` du mandataire ;
2. la seule adresse non locale de la machine est `192.0.2.2/24`, soit
   **TEST-NET-1** (RFC 5737), une plage de documentation non routable. Même
   avec la sortie ouverte, aucune validation entrante n'est possible : c'est
   Let's Encrypt qui ouvre la connexion vers le port 80.

Le second obstacle ne se contourne par aucun réglage : il n'est pas question
d'outillage mais de topologie. La conclusion utile n'est donc pas un banc de
plus, c'est **le contrôle à passer là où la réponse existe** — sur le
serveur. `deploy/verifier_tls.sh` vérifie le nom, le CAA, qui occupe le port
80, la sortie vers l'ACME et le certificat en place ; il dit aussi, en toutes
lettres, ce qu'il ne peut pas vérifier.

Il attrape en particulier la panne qui ne se voit pas de l'intérieur :
**quand l'ACME échoue, Caddy ne s'arrête pas — il signe avec son autorité
interne.** Le site répond en TLS, les journaux du serveur sont calmes, et
tous les navigateurs refusent.

Le script a été éprouvé dans les deux sens, ce qu'un contrôle mérite : il
approuve une machine saine (nom résolu, Caddy sur le port 80, certificat
lisible) et il refuse ce qu'il doit refuser — un serveur étranger posé sur le
port 80 est signalé par l'en-tête `Server`, et l'autorité interne est
signalée comme telle. Deux de ses propres défauts sont sortis de cette
épreuve : un code HTTP concaténé avec son repli (`000000`), et un `404`
attendu là où Caddy répond légitimement `308` hors émission.

### 9.9 Surveillance des erreurs — **IMPORTANT** : ce qu'un événement réel a révélé

L'intégration (décision 77) est éteinte tant qu'on ne lui donne pas
d'adresse. Pour vérifier ce qu'elle laisse sortir, un faux point d'entrée
Sentry a été monté sur le banc, l'adresse pointée sur lui, et une **vraie
erreur** provoquée — un dépôt vers un stockage injoignable. L'événement a
ensuite été lu, champ par champ.

**Les deux réglages annoncés ne suffisaient pas.** Avec
`send_default_pii=False` et `max_request_body_size="never"` déjà en place,
l'événement portait encore :

| ce qui partait | d'où |
|---|---|
| `uploaded_by='manager.banc'`, `validated_data` du sérialiseur | **variables locales** de chaque cadre de pile, jointes par défaut |
| `extra.compte` = le nom du déposant | `core.journalisation` attache le compte à **chaque ligne de journal** ; Sentry recopie les attributs d'un enregistrement |
| adresse du client | en-têtes `X-Forwarded-For` et `X-Real-Ip` — `send_default_pii` ne couvre que l'adresse vue de la socket |

Ce qui marchait déjà : la valeur de `Authorization` arrivait `[Filtered]`, et
le corps de la requête était vide.

**Corrigé** : `include_local_variables=False` et un `before_send` qui retire
les en-têtes porteurs d'adresse, le compte et l'adresse du contexte de
journal, et les arguments de la ligne de commande — `revoquer_sessions
--compte <nom>` les mettrait dans `sys.argv`, que Sentry joint de lui-même.
Rejoué sur la même erreur : plus de nom de compte, plus d'adresse de client,
et il reste l'exception, la pile avec le code source, le chemin de la
requête, la version, et l'identifiant de requête que l'utilisateur cite quand
il signale un incident.

La leçon dépasse Sentry : **une configuration de confidentialité ne se relit
pas, elle se mesure.** Les trois fuites étaient dans la documentation de
l'outil ; aucune n'était visible dans le code qui les configurait.

### 9.10 Deux machines réelles : pourquoi pas d'ici, et comment le mesurer là-bas

Demandé après la bascule sur banc. Vérifié plutôt que supposé : cette session
ne dispose que d'un environnement cloud, sans sortie TCP brute (SSH est
réécrit en HTTPS par le mandataire, un port quelconque expire), et une
seconde session serait un autre conteneur isolé en TEST-NET, incapable de
joindre le premier. Deux machines réelles ne s'opèrent donc pas d'ici, et un
troisième banc sur une seule machine n'aurait rien appris de plus.

Ce qui manquait pour que **vous** la jouiez n'était pas un script de plus
pour promouvoir — `promouvoir_replique.sh --repetition` existe —, c'était de
pouvoir la **mesurer**. Après une bascule, `curl /api/health/` rendait le
même corps quelle que soit la machine : rien ne disait laquelle avait servi,
alors que c'est la seule question. Deux ajouts, petits :

* `/api/health/` porte un champ `machine` quand `SERVEUR_NOM` est réglé —
  **absent sinon**, pour ne rien révéler de plus qu'avant ;
* `deploy/chronometrer_bascule.sh` interroge le domaine chaque seconde
  depuis un poste tiers, n'écrit qu'aux changements, et rend les trois durées
  du banc : première erreur, service rétabli, et **le retour d'une machine
  écartée**, qu'il signale en toutes lettres.

Éprouvé sur une séquence réelle (une application relancée sous trois noms
successifs) : il a vu « 1 2 1 », donné les durées, et déclenché l'alerte au
retour de 1. Deux de ses défauts en sont sortis : une expansion de shell qui
imprimait « +6 s6 », et une liste dédoublonnée qui cachait justement le
retour.

Les chiffres du banc sont une borne, pas une mesure : la première répétition
sur les vraies machines doit reporter les siens ici.

---

## 10. Limites connues, non couvertes

Écrites ici pour qu'elles ne se redécouvrent pas en production.

1. **Une base vivante au niveau TCP mais qui ne répond plus** — processus
   figé, ou machine dont le noyau acquitte encore. Mesuré : la requête pend
   **au-delà de 95 s**. `connect_timeout` ne s'applique pas à une connexion
   ouverte, `statement_timeout` est appliqué par le serveur — justement ce
   qui manque —, et les sondes TCP reçoivent leurs acquittements du noyau
   distant. **Aucun réglage de connexion ne peut y répondre.**

2. **Un conteneur déclaré malsain n'est pas relevé.** `restart:
   unless-stopped` redémarre un conteneur **sorti**, pas un conteneur
   enlisé. Le rétablissement reste manuel.

3. **La santé du conteneur n'est pas la santé des tâches.** Le battement de
   cœur de l'ordonnanceur ne touche pas la base : le conteneur reste sain
   pendant que ses six tâches échouent. C'est voulu (voir §7), mais la
   surveillance doit passer par le journal.

4. **Le remplissage délibéré du cache reste possible** depuis de nombreuses
   adresses — chaque nom de compte essayé crée une clé. Le correctif ferme
   le cas accidentel ; il faudrait aujourd'hui une quarantaine d'adresses
   pour le provoquer, la limite par adresse étant redevenue exacte.

5. **Scénarios non joués, faute de Docker sur le banc** : limites CPU et
   mémoire de conteneur, tueur de mémoire (OOM), disque plein, ordre de
   redémarrage des conteneurs. Ils restent à éprouver sur le serveur de
   préproduction.

6. **Réserve sur le scénario 15.** Les quinze invariants métier tiennent,
   mais l'un d'eux — « toute ligne sortie du brouillon est tracée » —
   signale les 6 009 lignes du banc : elles ont été créées directement en
   base par le script de remplissage, sans passer par `transitions.soumettre`,
   le seul chemin qui écrit le journal d'audit. C'est un défaut **du banc**,
   pas de l'application (62 entrées d'audit, aucune sur une ligne). La
   propriété reste donc à vérifier sur des lignes réellement soumises.

7. **Trois choses ne se jouent que sur le serveur**, et l'outil pour les
   vérifier là-bas est livré : **Let's Encrypt lui-même** (§9.8 bis —
   `deploy/verifier_tls.sh`), **deux machines réelles** (§9.10 —
   `deploy/chronometrer_bascule.sh`, `SERVEUR_NOM`), et **MinIO lui-même**
   (§9.7 — un autre serveur S3 a tenu sa place ; le chemin de l'application
   est éprouvé, pas le comportement propre de MinIO).

8. **Le retour d'une ancienne primaire n'est protégé par aucun programme**
   (§9.5). C'est une consigne d'exploitation, écrite dans
   `promouvoir_replique.sh` et tenue par un test ; départager deux bases
   demanderait un arbitre extérieur, non justifié pour un dispositif qui
   bascule à la main.

9. **Rien dans la suite de tests n'exécute Caddy** : l'invariant des
   variables vides (§9.4) est vérifié sur le texte des fichiers, pas par le
   programme qui les lit. Les deux `Caddyfile` ont été validés par Caddy
   2.8.4 sur le banc, dans chaque mode livré.

10. **Quatre en-têtes de sécurité sont servis en double** sur une réponse
    d'API — Django et nginx, nginx et Caddy (§9.8). Valeurs identiques,
    sans effet pratique ; noté, non corrigé, parce que choisir la source
    unique demande de décider ce qui protège les réponses que Django ne
    sert pas.

11. **L'interface n'est pas surveillée** (§9.9) : la politique de sécurité
    du contenu n'autorise que l'origine, et l'ouvrir à un tiers se décide.

---

## 11. Architecture : ce qui a été ajouté, et ce qui ne l'a pas été

```
                       Internet
                          │
                   ┌──────▼──────┐
                   │  aiguillage │  troisième machine — Caddy, lb_policy first,
                   │  (déc. 76)  │  /api/health/ toutes les 5 s, read_timeout 900 s
                   └──┬───────┬──┘
          machine 1   │       │   machine 2 (déc. 75)
      ┌───────────────▼──┐ ┌──▼───────────────┐
      │ Caddy · nginx    │ │ Caddy · nginx    │  application à l'arrêt
      │ gunicorn 2 × 4   │ │ (profil bascule) │  jusqu'à la promotion
      │ Redis ⊕ filet    │ │                  │
      │ (déc. 73)        │ │                  │
      │ PostgreSQL ──────┼─┼─▶ réplique       │  flux asynchrone, 0,69 ms
      │  index (déc. 72) │ │   (lecture seule)│  max_slot_wal_keep_size
      │  archivage WAL ──┼─┼─▶ reprise à      │
      │  (déc. 74)       │ │   l'instant      │
      │ MinIO            │ │                  │
      └──────────────────┘ └──────────────────┘
                  │
                  └── Sentry (déc. 77), éteint sans SENTRY_DSN
```

**La première série n'a ajouté aucun composant** : elle a posé des bornes.
**La seconde en a ajouté quatre**, et chacun a dû justifier son existence
par une mesure avant d'entrer — Redis parce que le cache en base écrivait à
chaque lecture, la réplique parce que le dump de 02:00 était la seule
reprise, l'aiguillage parce que le TTL du DNS décidait du retour du service,
Sentry parce que Grafana dit *que* la plateforme va mal et jamais *pourquoi*.
Chacun est **facultatif** ou **muni d'un filet** : la pile démarre sans
Redis, sans réplique, sans aiguillage et sans Sentry, exactement comme
avant.

Ce qui a été écarté après mesure, dans la seconde série comme dans la
première : un second index, une borne nginx relevée (mesurée pire), un
arbitre de bascule (Patroni, etcd), un statut 413 déterministe (une
troisième copie de la borne), la surveillance de l'interface (ouvrir la
politique de sécurité du contenu). La liste de la première série est au §7.

---

## 12. Bilan des deux séries

| | première série | seconde série | total |
|---|---|---|---|
| commits | 10 | 11 | **21** |
| tests ajoutés, vérifiés rouges avant | 60 | 94 | **154** |
| suite complète | 1 140 | 1 233 | **1 233**, verte |
| décisions consignées | 60 à 71 | 72 à 77 | **18** |
| défauts critiques corrigés | 2 | 0 | 2 |
| affirmations du dépôt démenties par la mesure | 1 (§6.3) | 4 | **5** |
| limites assumées, écrites | 1 | 4 | 5 |

Ce que l'audit n'a **pas** trouvé mérite autant d'être dit : aucun N+1,
aucun invariant métier rompu par le chaos, aucune perte de données sous
`SIGKILL` — ni sur une base seule, ni sur une primaire répliquée —, aucun
doublon d'e-mail avec deux ordonnanceurs, aucune amplification entre pannes
combinées, et un dépôt de 20 Mo identique octet pour octet à travers quatre
étages, en clair comme en TLS, sur disque comme sur stockage objet, seul
comme à huit en parallèle. Le cœur métier a tenu tout ce qu'on lui a fait
subir.

Ce que l'audit a appris sur lui-même, et qui vaut pour la suite : **une
garantie écrite n'en est pas une** — cinq fois, la mesure a contredit le
dépôt, et trois de ces cinq affirmations avaient été écrites pendant l'audit
lui-même. La seule protection contre cela est celle qui a été appliquée à
chaque fois : jouer la panne, lire ce qui sort, et ne corriger qu'ensuite.

---

## 13. Relecture après l'audit : ce que le banc n'avait pas pu jouer

Une fois les deux séries fusionnées, une relecture du dépôt — pas une
mesure, une lecture — a confronté ce que l'audit affirmait à ce que la pile
livrée faisait. Elle a trouvé, précisément dans ce que le banc n'avait pas
exécuté (§10.5 : pas de Docker, §10.9 : pas de seconde machine), une
troisième famille d'affirmations fausses : celles qu'aucune mesure n'avait
touchées parce qu'aucune mesure ne pouvait les atteindre.

| affirmation du dépôt | ce que la pile faisait | correction | décision |
|---|---|---|---|
| « la reprise à un instant donné se lance par le service `sauvegarde` » | le script n'était monté dans aucun conteneur ; le service ne voyait pas `pgdata` et tournait en root, que `pg_ctl` refuse | service `reprise` sous `postgres`, seul à voir les données, mode essai autonome, mise de côté compatible avec un point de montage | 79 |
| « les segments et les sauvegardes physiques partent hors machine comme les dumps » | la boucle de copie ne connaissait que `base` et `pieces` ; `demande-wal` n'était jamais lue | familles `base base-physique wal pieces`, un marqueur par famille, retard de copie surveillé | 78 |
| « la clé privée se donne par `SAUVEGARDE_CLE_PRIVEE=/run/secrets/…` » | aucun secret de ce nom dans la pile | la clé s'apporte sur la ligne de commande le jour venu, jamais dans `.env` | 79 |
| « Postgres archive dans le volume des sauvegardes » | le volume était créé en root ; l'archivage sous `postgres` ne pouvait pas y créer `base/wal` | `sauvegardes-init` donne le volume avant que la base ne démarre ; la CI le vérifie (`failed_count = 0`) | 79 |
| « une sauvegarde physique par semaine » | `pg_basebackup` depuis le service `sauvegarde` était refusé par `pg_hba.conf` (connexion de réplication, autorisée seulement depuis la machine) — trouvé par la première exécution du travail CI | entrée `host replication … samenet` à l'initialisation, commande unique pour un cluster existant, remède imprimé par le script | 79 |
| « la seconde machine suit la première » | le port 5432 n'était publié nulle part ; `pg_basebackup` attendu sur l'hôte ; promotion par `pg_ctl` en root | `docker-compose.primaire.yml` sur l'adresse privée, préparation dans le conteneur, `pg_promote()` | 80 |
| « une matrice modifiée s'applique à la requête suivante » | vrai sauf si Redis manquait à l'instant de l'enregistrement : l'ancienne matrice lui survivait sans expiration | expiration à 60 s et invalidation des deux caches | 81 |
| RPO « 24 h » ici, « quelques minutes » là | les deux étaient faux tant que les segments restaient sur la machine | un seul endroit, `deploy/README.md` | 82 |

**Ce qui n'a pas été mesuré, et reste à l'être** : l'espace disque réel
que consomment les segments sur le serveur (§10 ; borne écrite dans
`docs/infra-base-de-donnees.md` §3.A), et la bascule sur deux machines
réelles (§10.9), toujours pas répétée. La CI joue désormais la chaîne
archivage → sauvegarde physique → reprise sur la pile livrée à chaque
changement ; elle ne remplace pas la répétition trimestrielle sur le
serveur, elle garantit que ce qu'on y répète est ce qui est livré.

La leçon rejoint celle du §12, et la précise : une garantie écrite n'en est
pas une, **et une garantie mesurée sur un banc ne vaut que pour ce que le
banc a exécuté**. Ce qui n'est joué ni par une mesure ni par la CI doit
être lu comme une promesse, et dit comme tel.
