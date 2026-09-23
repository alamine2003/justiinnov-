# Recette manuelle de JUSTI INNOV

Ce document sert à deux choses : **comprendre** l'application assez pour la
présenter et la modifier, et la **tester à la main**, compte par compte, sur un
jeu de données qui couvre les dix-sept filiales et chaque état du circuit.

La recette se fait **sur la pile locale**, jamais sur la préproduction ni la
production : rien ne se supprime dans cette application, un jeu de test posé
sur une base réelle y resterait pour toujours. La commande qui remplit la base
le refuse d'elle-même hors du mode debug.

---

## 1. L'application en dix minutes

### Ce qu'elle fait, et ce qu'elle ne fait pas

JUSTI INNOV suit les dépenses des filiales africaines d'INNOV PHARMA et leurs
justificatifs. **Elle n'autorise pas une dépense** : l'argent est déjà dépensé
quand on la déclare. Elle répond à quatre questions : *qu'est-ce qui a été
dépensé, quand, où, au profit de qui — et où est la preuve ?*

### Les trois rôles

| Rôle | Qui | Ce qu'il fait |
|---|---|---|
| `manager` | le pays | **déclare**, seul : ouvre les dossiers de son pays, saisit ses dépenses, joint les pièces, soumet, importe |
| `admin` | RH, au siège | **contrôle**, seul, jusqu'à la clôture : met en contrôle, justifie ou refuse, clôture, rouvre, décide des rectifications ; tient les comptes, le référentiel, l'audit, les exports ; **lit** les enveloppes |
| `super_admin` | direction | **supervise et alloue** : voit tout, relit l'audit, administre ; seul, attribue, modifie et supprime les enveloppes, arbitre les réallocations (décision 91) ; ne déclare ni ne contrôle |

Ni l'administrateur ni le super administrateur ne créent de dossier ni ne
déposent de pièce. Un dossier appartient à **un pays**, pour toujours : seul
ce pays le remplit. Un `manager` rattaché à une **équipe** ne voit que ses
dossiers ; sans équipe, tout son pays.

### Le circuit d'une dépense

```
brouillon → soumis → en contrôle → justifié / non justifié → clôturé
```

- Un **dossier** porte un numéro d'ordre et regroupe des **lignes** (les
  dépenses) et des **pièces** (factures, reçus).
- **Une dépense soumise est irréversible** : elle ne revient plus au
  brouillon, ne se modifie plus, ne se supprime pas. Seul un brouillon, jamais
  soumis, se retire — et seulement par son auteur.
- **Deux exceptions, tracées et motivées** : la **réouverture** (la RH renvoie
  au pays un dossier soumis pour qu'il le corrige) et la **rectification** (le
  pays demande de revoir une ligne déjà constatée, un administrateur qui n'est
  pas le demandeur décide).
- **Deux personnes** : le pays déclare, l'administrateur contrôle ; personne
  ne justifie ce qu'il a saisi.

### L'argent : enveloppes, engagé, consommé, justifié

- Chaque pays a une **enveloppe** par année, et peut avoir des
  **sous-enveloppes** (par équipe, projet ou manager).
- Une ligne **soumise** ou **en contrôle** est **engagée** ; une ligne
  **justifiée**, **non justifiée** ou **clôturée** est **consommée**. Une
  dépense non justifiée pèse quand même sur l'enveloppe : l'absence de preuve
  ne fait pas revenir l'argent. L'**écart** entre consommé et justifié dit ce
  qui manque de preuve.
- Le **niveau d'exécution** d'une enveloppe (normal, alerte, dépassement) est
  calculé **par le serveur** à partir des seuils de la configuration ;
  l'interface ne recalcule rien.
- Quand une dépense ferait dépasser l'enveloppe, la **politique** de
  l'enveloppe décide : alerter, bloquer, ou soumettre à approbation.

### Ce qui rend l'application digne de confiance

- **Cloisonnement** : un compte ne voit que son périmètre, vérifié par le
  serveur. Un dossier d'un autre pays répond « introuvable », pas « interdit ».
- **Traçabilité** : toute action sensible laisse une trace — qui, quoi, quand,
  depuis quelle adresse, avant et après. Rien ne s'efface.
- **Droits réglables** : chaque action est une « capacité » que la RH attribue
  aux rôles dans *Configuration › Permissions*, avec trois verrous que
  personne ne lève : le pays seul déclare, l'administrateur seul contrôle, les
  administrateurs gardent l'administration.

Pour aller plus loin : `CLAUDE.md` (les règles), `docs/model-de-donnees.md`
(le modèle et les décisions numérotées), `DESIGN.md` (l'interface).

---

## 2. Préparer la recette

Sur ton poste, dans le dépôt :

```bash
docker compose up -d
docker compose exec backend python manage.py seed_recette --base-jetable
```

Compter une trentaine de secondes. La commande affiche le **mot de passe commun
à tous les comptes** et l'écrit dans `backend/recette.local.md`, avec la liste
des comptes. Ce fichier n'est jamais versionné.

Ouvrir <http://localhost:5173>. **Aucun e-mail ne part** : le courrier est
coupé par défaut (décision 88). Les notifications se lisent dans la cloche du
bandeau, compte par compte.

### Ce que le jeu contient

- **17 pays**, chacun dans sa devise : FCFA (Afrique de l'Ouest et centrale),
  ariary (Madagascar), franc guinéen, ouguiya (Mauritanie), dalasi (Gambie),
  franc de Djibouti, franc congolais (RDC). Les taux de change sont
  **fictifs**, sauf la parité de l'euro.
- Par pays : deux équipes (la première porte le nom de la capitale), un
  projet, un client, un prospect, une enveloppe et une sous-enveloppe pour la
  première équipe.
- **37 comptes**, préfixés `recette.` :

| Compte | Rôle | Périmètre |
|---|---|---|
| `recette.dg` | super_admin | tout |
| `recette.do` | super_admin | tout — tranche les réallocations de `recette.dg` |
| `recette.rh` | admin | tout |
| `recette.<pays>.manager` | manager | le pays entier (`<pays>` = `tg`, `sn`, `ci`…) |
| `recette.<pays>.equipe` | manager | la première équipe du pays seulement |

- Par pays, **8 dossiers** numérotés `R-<PAYS>-01` à `08` :

| N° | Équipe | État | Ce qu'il permet de tester |
|---|---|---|---|
| 01 | 2 | brouillon du manager du pays | soumettre ; au Mali, la soumission est **bloquée** par l'enveloppe |
| 02 | 1 | brouillon du manager d'équipe | le manager du pays **ne peut pas** le soumettre |
| 03 | 1 | soumis, avec pièce | mise en contrôle et réouverture par la RH |
| 04 | 2 | en contrôle | justification ou refus par la RH |
| 05 | 1 | en contrôle, deux lignes justifiées (dont une à moitié), une ligne payée en euros en attente | justification partielle, conversion de devise ; **ne se rouvre plus** |
| 06 | 2 | non justifié, soumis sans pièce | motif du refus, écart consommé / justifié |
| 07 | 1 | clôturé, avec une **demande de rectification en attente** | décision de rectification par un administrateur |
| 08 | 2 | rouvert par la RH puis resoumis, pièce remplacée | motif de réouverture, versions de pièce |

- **Enveloppes calibrées** : Sénégal, Cameroun et Madagascar **en alerte**,
  Guinée et RDC **en dépassement**, Mali en politique **« bloquer »**, les
  autres à l'aise.
- **Réallocations** demandées par `recette.dg` : une en attente au Togo, au
  Sénégal et au Cameroun ; une approuvée et une refusée au Togo par
  `recette.do` — nul ne tranche sa propre demande.
- **Taux de change** : un taux en euros daté du **mois prochain**, qui ne doit
  pas être « en vigueur ».

---

## 3. Les parcours, compte par compte

Chaque ligne dit quoi faire et ce qu'on doit observer. Cocher au fur et à
mesure ; noter tout écart avec le compte, le dossier et une capture.

### Manager du pays — `recette.tg.manager`

- [ ] **Pilotage** ne montre que le Togo, en FCFA.
- [ ] **Dossiers** : les huit dossiers togolais, aucun autre pays.
- [ ] `R-TG-01` : soumettre. *Attendu* : le dossier passe « soumis », ses deux
      lignes partent avec lui, il n'est plus modifiable.
- [ ] `R-TG-02` (brouillon du collègue) : *attendu* — pas de bouton
      « Soumettre », pas de « Modifier » ni « Supprimer ».
- [ ] Créer un dossier, ajouter une ligne, joindre un PDF, soumettre.
      *Attendu* : une seule action suffit à tout déclarer.
- [ ] Créer un dossier **sans pièce** et le soumettre. *Attendu* : un
      avertissement, mais la soumission passe.
- [ ] Essayer de joindre un fichier texte renommé en `.pdf`. *Attendu* : refusé.
- [ ] `R-TG-05`, ligne justifiée : **demander une rectification** avec un
      motif. *Attendu* : la demande apparaît « en attente » ; le motif est
      obligatoire.
- [ ] **Importer** (sur la liste des dossiers) : simuler l'import d'un
      classeur du Togo. *Attendu* : le compte rendu de la simulation, rien
      d'écrit ; une équipe inconnue est refusée, il faut la demander à la RH.
- [ ] Aucune entrée **Audit**, **Configuration**, **Pays** dans le menu.
- [ ] **Cloisonnement** : avec `recette.dg`, ouvrir `R-SN-03` et copier son
      adresse ; la coller dans la session du manager togolais. *Attendu* :
      « introuvable ».

### Manager d'équipe — `recette.tg.equipe`

- [ ] **Dossiers** : seulement 02, 03, 05 et 07 (équipe Lomé).
- [ ] `R-TG-02` : il peut le modifier, le supprimer, le soumettre.

### Manager du Mali — `recette.ml.manager`

- [ ] Soumettre `R-ML-01`. *Attendu* : refus, avec le montant du dépassement
      et le nom de l'enveloppe.

### Administrateur (RH) — `recette.rh`

- [ ] **Dossiers** : filtrer par pays avec « Tous les pays » ; l'adresse
      garde le choix (`?country=`).
- [ ] Ni **Nouveau dossier** ni **Importer** : le siège ne déclare pas.
- [ ] `R-SN-03` : **mettre en contrôle**. *Attendu* : le dossier passe « en
      contrôle ».
- [ ] `R-TG-04` : justifier une ligne, **refuser** l'autre. *Attendu* : le
      refus exige un motif.
- [ ] Justifier une ligne **en partie** (montant inférieur) : l'écart apparaît
      sur l'enveloppe.
- [ ] Justifier puis **clôturer** un dossier dont toutes les lignes sont
      tranchées. *Attendu* : pas de clôture tant qu'une ligne est en suspens.
- [ ] `R-TG-05`, ligne en euros : le montant d'origine (150 EUR), le taux et
      le montant en FCFA sont affichés.
- [ ] `R-TG-03` : **rouvrir** avec un motif. *Attendu* : le dossier revient au
      brouillon, le motif est affiché, le manager du Togo est notifié.
- [ ] `R-TG-05` : **pas de réouverture possible** — une ligne est déjà
      justifiée, le siège a constaté.
- [ ] `R-TG-07` : décider la **rectification** demandée par le manager, sur
      la fiche du dossier. Approuvée, *attendu* : la ligne revient **en
      contrôle**, pas au brouillon, montant justifié à zéro.
- [ ] **Budgets** : il **lit** les enveloppes et leur consommation, sans
      bouton « Attribuer », « Modifier » ni « Supprimer », ni décision sur
      une réallocation — les enveloppes sont à la direction (décision 91).
- [ ] Une ligne en **dépassement** sous politique « soumettre à
      approbation » : la justifier est refusé tant que la direction n'a pas
      abondé l'enveloppe.
- [ ] **Configuration › Général**, taux de change : consultables, le taux en
      euros du mois prochain est « historique », celui du 1er janvier « en
      vigueur » ; aucun ajout possible.
- [ ] **Configuration › Permissions** : les lignes de la déclaration et du
      contrôle sont figées. Retirer au pays la demande de rectification, se
      reconnecter en manager, constater que le bouton « Rectifier » a
      disparu ; la remettre.
- [ ] **Configuration › Utilisateurs** : créer un compte ; l'adresse doit
      être en `@innovpharma.net`, et une adresse déjà prise est refusée.
- [ ] **Audit** : retrouver la réouverture, la rectification et la
      réallocation, avec l'auteur, l'heure et l'avant / après.
- [ ] **Exports** (menu d'export du Pilotage, des Dossiers ou du Registre) : un export
      Excel du Togo, puis un PDF. Avec un compte manager, le menu n'existe
      pas.

### Super administrateur (direction) — `recette.dg`

- [ ] **Dossiers** : tous les pays, filtrables ; ni création, ni import.
- [ ] Ouvrir `R-TG-04` : **aucun** bouton de contrôle — il supervise, il ne
      tranche pas. Pas de « Rouvrir » non plus.
- [ ] **Audit** : il relit les décisions de la RH.

- [ ] **Pilotage** consolidé en FCFA : Sénégal, Cameroun, Madagascar en
      **alerte** ; Guinée et RDC en **dépassement** ; les autres normaux.
- [ ] La Guinée affiche ses montants en francs guinéens, la RDC en francs
      congolais.
- [ ] Réallocation en attente du Togo : **pas de décision possible** — il l'a
      demandée lui-même.
- [ ] **Budgets** : attribuer une sous-enveloppe à la seconde équipe d'un
      pays, puis la **supprimer** : le bouton « Supprimer » n'apparaît que
      sur une enveloppe qui n'a jamais servi, et l'historique garde la
      suppression. Sur l'enveloppe du Togo, qui porte des dépenses, pas de
      « Supprimer » : elle se désactive.

### Super administrateur (opérations) — `recette.do`

- [ ] **Budgets › Réallocations** : approuver celle du Sénégal, refuser celle
      du Cameroun avec un motif.

### Partout

- [ ] Changer la langue en **English** depuis le sélecteur de langue :
      toute l'interface suit, messages d'erreur du serveur compris.
- [ ] La **cloche** montre les notifications propres à chaque compte.
- [ ] Thème sombre : tout reste lisible.

---

## 4. Tout retirer

Le jeu de recette ne se retire pas par l'application — rien ne s'y supprime,
c'est la règle. Il se retire **en jetant la base locale** :

```bash
docker compose down -v
rm backend/recette.local.md
```

`-v` efface les volumes de la pile locale : la base, les pièces (MinIO) et le
cache. **C'est toute la pile locale** qui repart à zéro, pas seulement la
recette. Un `docker compose up -d` redonne une base vide, prête pour une
nouvelle recette.

Ni la préproduction ni la production ne sont touchées : elles tournent sur le
serveur, avec leurs propres volumes.
