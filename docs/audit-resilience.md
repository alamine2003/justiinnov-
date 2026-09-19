# Audit de résilience — JUSTI INNOV

Septembre 2026. Dix phases, injection de pannes réelles sur un banc dédié.

Ce document est le compte rendu complet : ce qui a été éprouvé, ce qui a
cédé, ce qui a tenu, ce qui a été corrigé, ce qui ne l'a pas été et
pourquoi. Les décisions elles-mêmes vivent dans
[`model-de-donnees.md`](model-de-donnees.md) §8, numéros **60 à 71** ; on
les référence ici sans les recopier.

**Tous les chiffres de ce document ont été mesurés.** Aucun n'est estimé.
Quand une mesure manque, c'est écrit.

---

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
| **MinIO** | dépôt et téléchargement de pièces | perte **bornée** : 503 en 31–34 s, reste de l'API intact (déc. 60) |
| **gunicorn** | API | worker abattu : perte des seules requêtes en vol, renaissance en 0,39 s |
| **ordonnanceur** | relances d'e-mails, alertes, contrôle des sauvegardes | **dégradation seulement** : les files sont des tables, le travail attend |
| **nginx / Caddy** | accès | non éprouvé (hors périmètre du banc) |

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
| 6 | Base figée (`SIGSTOP`) | **ÉCHEC — non corrigé** | Toujours > 95 s ; aucun réglage ne peut y répondre (§9) |
| 7 | Stockage muet | **ÉCHEC** | Toute l'API muette, sans reprise |
| 8 | Serveur de courrier mort | **PARTIEL** | Mécanisme sain, abandon final silencieux |
| 9 | Deux ordonnanceurs simultanés | **RÉUSSITE** | 60 envoyés, 60 reçus, **0 doublon** |
| 10 | Amplification pendant une panne | **PARTIEL** | 5,7× de débit, et 24 Mo de journaux en 7 s |
| 11 | Volume (9 → 6 009 lignes) | **RÉUSSITE** | Aucun N+1 ; le coût vient d'ailleurs (§5) |
| 12 | `EXPLAIN` sur `/api/expenses/` | **ÉCHEC** | Planification 91 ms pour 43 ms d'exécution |
| 13 | Limite de connexion sous concurrence | **ÉCHEC** | 5 annoncées, 13 passées |
| 14 | Purge du cache | **ÉCHEC** | 400 comptes actifs effaçaient l'anti-bourrage |
| 15 | Invariants métier après chaos | **RÉUSSITE** | 15 invariants, tenus (réserve en §9) |
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

## 9. Limites connues, non couvertes

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

---

## 10. Architecture proposée

```
                    Internet
                       │
                  ┌────▼─────┐
                  │  Caddy   │
                  └────┬─────┘
                  ┌────▼─────┐
                  │  nginx   │  limit_req 40 r/s par IP
                  └────┬─────┘
              ┌────────▼─────────┐
              │    gunicorn      │  2 × 4 fils
              │                  │  ⊕ vidange 35 s (déc. 64)
              │                  │  ⊕ 503 + Retry-After (déc. 62)
              │                  │  ⊕ journal nommé, borné (déc. 61, 63)
              └───┬──────────┬───┘
                  │          │
    connexion 3 s │          │ connexion 3 s, lecture 10 s,
    requête 15 s  │          │ 2 tentatives (déc. 60)
    verrou 10 s   │          │
    (déc. 70)     │          │
         ┌────────▼───┐  ┌───▼────────┐
         │ PostgreSQL │  │   MinIO    │
         │ max_conn 50│  └────────────┘
         │ (déc. 66)  │
         │ cache 2000 │
         │ (déc. 69)  │
         └─────┬──────┘
               ├──── ordonnanceur ──── abandons signalés (déc. 65)
               └──── sauvegardes ───── 3 places réservées au propriétaire
```

**Aucun composant n'est ajouté, aucun n'est retiré.** C'est la conclusion de
l'audit, et elle mérite d'être dite franchement : l'architecture était juste
pour cette charge. Ce qui manquait n'étaient pas des **briques**, c'étaient
des **bornes** — chaque attente était infinie, et chaque panne partielle
devenait donc un arrêt total.

Les douze décisions ajoutent des limites, des journaux et des verrous. Elles
n'ajoutent pas une seule dépendance.

---

## 11. Bilan

- **10 commits**, **60 tests ajoutés** — chacun vérifié rouge sur le code
  d'avant —, suite complète à **1 140 tests**, verte ;
- **12 décisions** consignées (60 à 71) ;
- **2 défauts critiques** corrigés, chacun transformant une panne partielle
  en arrêt total sans reprise ;
- **2 défauts de sécurité** corrigés sur la protection anti-bourrage ;
- **1 défaut introduit par un correctif**, trouvé en remesurant, et corrigé ;
- **1 limite assumée**, écrite noir sur blanc.

Ce que l'audit n'a **pas** trouvé mérite autant d'être dit : aucun N+1,
aucun invariant métier rompu par le chaos, aucune perte de données sous
`SIGKILL`, aucun doublon d'e-mail même avec deux ordonnanceurs simultanés,
et aucune amplification entre pannes combinées. Le cœur métier — le circuit
de justification, les verrous, l'atomicité des transitions — a tenu tout ce
qu'on lui a fait subir.
