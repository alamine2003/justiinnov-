# Infrastructure de la base de données — état et proposition

Septembre 2026. Ce document part des mesures de l'audit de résilience
([`audit-resilience.md`](audit-resilience.md)) et de ce que la pile fait
réellement aujourd'hui. Il propose une trajectoire, pas une refonte.

**Tous les chiffres sont mesurés.** Les extrapolations sont dites comme
telles.

---

## 1. Ce que les mesures disent — et ce qu'elles ne disent pas

| mesure | valeur |
|---|---|
| Base entière, avec **6 009 lignes de dépense** (≈ dix ans de l'activité attendue des dix-sept filiales) | **15 Mo** |
| Table la plus lourde (`expenses_expense`, index compris) | 2 008 ko |
| Débit servi, 16 clients simultanés | 62 req/s, 0 erreur |
| Connexions ouvertes par le serveur | **8**, exactement `workers × threads` |
| Coût mémoire d'une connexion | 1,9 à 2,4 Mo |
| Budget de la pile | 25 connexions sur 50 |
| Écriture par `GET`, depuis Redis (décision 73) | **0 octet** |

> **Ce n'est pas un problème de dimensionnement.** Une base de quinze
> mégaoctets tient dans les tampons partagés (256 Mo) : elle est
> intégralement en mémoire. Doubler, tripler la machine ne changerait rien
> aux chiffres ci-dessus, parce qu'aucun d'eux n'est limité par la base.

Les justificatifs, eux, ne sont pas dans la base : ils vivent dans MinIO.
C'est **là** que le volume grandira, pas ici. Un dossier de dépenses pèse
quelques kilo-octets en base et plusieurs méga-octets en pièces jointes.

**Extrapolation, dite comme telle** : à cent mille lignes — dix fois le
volume de dix ans —, la table passerait à environ 33 Mo, et l'index de tri
(décision 72) garde le coût d'une page de liste à 0,018 ms, mesuré à
600 000 lignes. La base n'est pas le mur.

---

## 2. Le vrai risque : la reprise, pas la performance

Ce que la pile fait aujourd'hui :

| | dispositif | mesuré / constaté |
|---|---|---|
| Sauvegarde | `pg_dump -Fc` quotidien à 02:00, chiffré AES-256 à la sortie du tube | rotation 30 jours, copie mensuelle **jamais supprimée** |
| Copie hors machine | `rclone crypt`, incrémentale, vérifiée (`rclone check`) | chiffrée en transit et au repos distant |
| Justificatifs | miroir séparé | même chaîne |
| Contrôle | `manage.py verifier_sauvegardes` lit les marqueurs, notifie les administrateurs | tâche de l'ordonnanceur |
| Restauration | `restaurer.sh`, depuis le volume ou depuis la copie distante | script écrit et documenté |

C'est une chaîne sérieuse, et plus complète que ce qu'on voit d'ordinaire à
cette échelle. Mais elle a **un trou, et il est béant** :

> **Il n'y a pas d'archivage des journaux de transaction.** Pas
> d'`archive_mode`, pas de `restore_command`, pas de sauvegarde continue.
> La seule granularité de reprise est le dump quotidien.

Conséquence, en clair : **une panne de disque à 01:59 perd toute la journée
de travail.** Toutes les dépenses saisies, toutes les pièces rattachées,
toutes les décisions du siège, tous les journaux d'audit de la journée.

Pour une application dont la raison d'être est « savoir ce qui a été
dépensé, et où est la preuve », c'est le risque le plus sérieux de toute
l'infrastructure — bien avant la performance. Et il n'est écrit nulle
part : ni `RPO` ni `RTO` n'apparaissent dans `deploy/README.md`.

### Ce que ces deux mots veulent dire, pour la direction

- **RPO** — ce qu'on accepte de **perdre**. Aujourd'hui : **jusqu'à 24 h**.
- **RTO** — le temps qu'on met à **repartir**. Aujourd'hui : non mesuré.
  `restaurer.sh` existe, mais une restauration n'a jamais été chronométrée
  sur le serveur réel. Un plan de reprise jamais joué n'est pas un plan.

---

## 3. Options, ce qu'elles coûtent et ce qu'elles achètent

### A. Archivage continu des journaux (PITR) — **recommandé**

`archive_mode = on`, les segments WAL poussés vers le même stockage
distant que les dumps, et une sauvegarde de base hebdomadaire
(`pg_basebackup`).

- **Achète** : RPO de 24 h → **quelques minutes**. Et la reprise à un
  instant précis, ce qui répare aussi l'erreur humaine — « restaurer la
  base telle qu'elle était juste avant l'import de mardi ».
- **Coûte** : un réglage Postgres, un script d'archivage, du volume
  distant. Le trafic WAL est faible, et il vient de baisser : depuis
  Redis, une lecture n'écrit plus rien (décision 73) ; il ne reste que les
  écritures métier réelles.
- **Ne change pas** : l'architecture. Un composant en plus, aucun.

### B. Réplique en lecture sur la même machine — **écarté**

- **N'achète rien** : même disque, même hôte, même panne. Une réplique sur
  la même machine protège d'une corruption logique de la primaire, pas
  d'une panne de la machine — et le vrai point de défaillance unique de
  cette pile, c'est l'hôte.
- **Coûte** : de la mémoire prise à une base qui n'en manque pas.

### C. Réplique en attente chaude sur une seconde machine — **plus tard**

- **Achète** : RTO de quelques minutes, survie à la perte d'une machine.
- **Coûte** : une seconde machine, une bascule à écrire **et à répéter**,
  et un exploitant qui sait la déclencher. Pour une équipe d'une personne,
  une bascule jamais répétée est un piège : elle se déclenche mal, le jour
  où tout va mal.
- **Quand** : quand l'indisponibilité d'une demi-journée deviendra
  inacceptable pour la direction. Ce n'est pas une décision technique,
  c'est une décision de service — et elle se prend avec un chiffre, pas
  avec une intuition.

### D. Base hébergée chez un tiers (« managed ») — **attention, mesuré**

- **Achète** : sauvegardes, PITR et bascule tenus par quelqu'un d'autre.
  Réel, et pour une équipe d'une personne, ce n'est pas rien.
- **Coûte, et le chiffre est mesuré** : la latence réseau. La pile actuelle
  parle à un conteneur voisin, **0,09 ms d'aller-retour**. Une base
  hébergée ailleurs se compte en millisecondes, et l'audit a mesuré où le
  coût bascule :

  | aller-retour | page de dépenses |
  |---|---|
  | 0,6 ms | 58 ms |
  | 11,8 ms | 266 ms |
  | 21,4 ms | 445 ms |
  | 51,6 ms | 1 016 ms |

  Au-delà de **10 ms**, le choix de charger les relations par préchargement
  plutôt que par jointure (décision 67) s'inverse, et il faudrait le
  reprendre. Au-delà de 25 ms, le débit sous seize clients tombe de 50 à
  6,9 req/s — **mesuré**, avec zéro erreur mais des pages à deux secondes.

  **Donc** : une base hébergée dans la même région que le serveur
  applicatif peut se défendre. Une base hébergée dans une autre région se
  paie sur chaque écran, tous les jours. Si cette piste est retenue,
  l'aller-retour se mesure **avant** de migrer, pas après.

---

## 4. Trajectoire proposée

Dans cet ordre, parce que chaque étape rend la suivante moins urgente.

**1. Dire ce qu'on garantit.** Écrire le RPO et le RTO visés dans
`deploy/README.md`, et les faire valider par la direction. Sans ce chiffre,
toutes les décisions qui suivent sont des goûts personnels. C'est gratuit
et c'est ce qui manque le plus.

**2. Chronométrer une restauration réelle** sur le serveur, depuis la copie
distante, avec `restaurer.sh`. On saura alors le RTO au lieu de l'espérer.
À refaire à chaque changement d'infrastructure — un plan de reprise se
répète.

**3. Archiver les journaux de transaction** (option A). C'est le seul
changement qui déplace vraiment le risque : de « perdre une journée » à
« perdre quelques minutes ».

**4. Surveiller ce qui est déjà en place.** `postgres-exporter` alimente
déjà Prometheus ; ajouter une alerte sur l'âge de la dernière sauvegarde
réussie et sur le retard d'archivage. `verifier_sauvegardes` notifie déjà
les administrateurs : vérifier que quelqu'un lit ces notifications.

**5. Réévaluer la haute disponibilité** (option C) quand le RPO/RTO écrit
à l'étape 1 ne sera plus tenu par les étapes 2 à 4. Pas avant.

---

## 5. Dimensionnement, pour mémoire

Les réglages actuels, et ce qui les justifie :

| réglage | valeur | pourquoi |
|---|---|---|
| `mem_limit` | 1 Go | base de 15 Mo entièrement en cache |
| `shared_buffers` | 256 Mo | un quart de la limite |
| `effective_cache_size` | 768 Mo | les trois quarts |
| `max_connections` | 50 | budget mesuré de la pile : 25 (décision 66) |
| `shm_size` | 256 Mo | les 64 Mo par défaut de Docker font échouer les tris parallèles |
| `statement_timeout` | 15 s | cent fois la requête la plus lourde mesurée (décision 70) |
| `lock_timeout` | 10 s | une transition tient son verrou 8,5 ms |

**Rien de tout cela n'a besoin de changer aujourd'hui**, et c'est une bonne
nouvelle : le budget et l'attention doivent aller à la reprise, pas à la
puissance.

---

## 6. Ce que je ne propose pas, et pourquoi

| écarté | mesure qui le justifie |
|---|---|
| **Gestionnaire de connexions (pgbouncer)** | Le serveur ouvre exactement `workers × threads` connexions — 8 sur 50. La borne est structurelle : il n'y a pas le problème que pgbouncer résout |
| **Partitionnement des tables** | La table la plus lourde fait 2 Mo. Le partitionnement se justifie à partir de dizaines de millions de lignes ; on en est à six mille |
| **Réplique en lecture pour soulager la primaire** | La primaire n'est pas chargée : 62 req/s, zéro erreur, et la saturation de quatre cœurs ne change pas le débit |
| **Index supplémentaires** | Mesurés un par un. Un seul était justifié (décision 72) ; un second candidat n'était jamais choisi par le planificateur et se serait pourtant payé à chaque écriture |
| **Grossir la machine** | Aucune des mesures n'est limitée par la base. On paierait une facture pour un chiffre qui ne bougerait pas |
