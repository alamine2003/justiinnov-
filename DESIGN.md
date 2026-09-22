# DESIGN.md — système d'interface de JUSTI INNOV

> Référence unique de l'interface. **À lire avant toute modification d'écran.**
> Les tokens vivent dans `frontend/src/index.css` ; ce document dit comment
> s'en servir.

L'application sert le siège — DM, DF, RH, direction — et les managers des
filiales, qui lisent des chiffres et cherchent des preuves, sur un poste de
travail — dans un navigateur ou dans l'application de bureau installée
(PWA) ; l'usage sur téléphone n'est pas un cas prévu. Trois principes en
découlent :

1. **La lisibilité prime sur l'effet.** Pas d'ornement qui n'aide pas à lire un
   montant, un statut ou une date.
2. **Rien ne se calcule dans l'interface.** Soldes, écarts et taux viennent du
   serveur ; l'interface formate, elle ne recalcule pas.
3. **Un écran n'est fini qu'une fois regardé.** La boucle de vérification
   visuelle fait partie du travail, pas de la relecture.

---

## Couleurs

Palette **neutre**, définie en `oklch` dans `frontend/src/index.css`, avec
un thème clair et un thème sombre. **N'écrivez jamais une couleur en dur** pour
un fond, un texte ou une bordure.

| Usage | Classe |
|---|---|
| Fond de page | `bg-background` |
| Surface : carte, dialogue, popover | `bg-card`, `bg-popover` |
| Texte principal | `text-foreground` |
| Texte secondaire, légendes | `text-muted-foreground` |
| Bordures | `border-border`, le plus souvent `border-border/60` |
| Action principale | `bg-primary text-primary-foreground` |
| Fond discret, survol | `bg-muted`, `hover:bg-accent` |
| Erreur, danger | `text-destructive`, `bg-destructive/10`, `border-destructive/20` |
| Anneau de focus | `focus-visible:ring-ring` |
| Voile derrière un dialogue ou un panneau | `bg-overlay` (10 % clair, 45 % sombre : un voile noir sur fond sombre est invisible) |
| Ombre portée d'une carte | `shadow-ombre` (jamais `shadow-black/…`) |

### Couleurs de la marque — liste close

L'identité d'INNOV PHARMA porte un azur, un corail, un ambre et un marine.
Ils ne remplacent pas les neutres — le gris reste la matière de l'écran —
mais ils donnent leur teinte aux **chiffres** : ce que montre une jauge, une
courbe ou une barre, et rien d'autre. **N'ajoutez aucune autre teinte** et
n'employez pas celles-ci pour du texte courant ou une grande surface.

| Sens | Jeton |
|---|---|
| Azur de la marque : trait de courbe, anneau de jauge, part consommée | `bg-marque`, `text-marque`, `fill-marque`, `stroke-marque` |
| Sur l'azur : encre marine, jamais blanche (`--marque-foreground`) | `text-marque-foreground` |
| Azur foncé : texte et lien lisibles sur fond clair | `text-marque-fort`, `bg-marque-fort text-marque-fort-foreground` |
| Azur clair : part engagée, seconde série | `bg-marque-clair` |
| Marine : le bandeau consolidé du Pilotage et le panneau de l'écran de connexion | `bg-banniere text-banniere-foreground` |
| Sur le marine : étiquette, chiffre mis en avant, filet | `text-banniere-muted`, `text-banniere-accent`, `bg-banniere-bordure` |

Le corail et l'ambre n'ont pas de jeton à eux : ce sont désormais
`--destructive` (écart, dépassement, non justifié) et `--statut-attente`
(en contrôle, incomplet, en attente) dans `index.css`. Une teinte de plus
aurait dit la même chose deux fois. L'ambre s'encre de marine
(`--statut-attente-foreground`) : le blanc n'y tenait pas le contraste.

Les cinq `--chart-*` descendent l'azur : une même famille se lit comme une
même grandeur à des intensités différentes.

### Couleurs de statut — liste close

Seule dérogation aux tokens, parce qu'un statut doit se reconnaître d'un coup
d'œil. **N'ajoutez aucune autre teinte.**

| Sens | Teinte |
|---|---|
| Justifié, actif, validé, approuvé | `bg-statut-succes text-statut-succes-foreground` |
| En contrôle, alerte, incomplet, en attente | `bg-statut-attente text-statut-attente-foreground` |
| Soumis, information | `bg-statut-info text-statut-info-foreground` |
| Brouillon | `bg-statut-neutre text-statut-neutre-foreground` |
| Archivé, clôturé | `bg-statut-archive text-statut-archive-foreground` |
| Non justifié, rejeté, dépassement | `bg-destructive text-destructive-foreground` |

`text-white` est proscrit sur un fond de statut : le jeton
`*-foreground` porte l'encre, et chaque paire tient **4,5:1 dans les deux
thèmes** — un badge est en `text-xs`, donc du texte normal au sens WCAG.

Le blanc ne s'écrit pas non plus *par le jeton* : l'émeraude du succès
(2,47:1), le bleu de l'information (3,76:1) et l'azur de la marque (3,10:1)
l'ont eu, et le grep sur la classe `text-white` ne pouvait pas le voir. Les
deux premiers ont été assombris ; l'azur et le corail, couleurs de la marque,
n'ont pas bougé — c'est leur encre qui a changé. Le test
`status-badge.test.tsx` calcule désormais le contraste de chaque paire depuis
`index.css`, `:root` et `.dark`, et échoue sous 4,5:1.

Les teintes sont centralisées dans `lib/status-styles.ts`, les badges dans
`components/expenses/status-badge.tsx` (`StatusBadge`, `ProofStatusBadge`,
`ProjectStatusBadge`, libellé serveur `*_display` prioritaire) et les tables
`*_LABELS` dans `lib/labels.ts`, traduites dans les deux langues. Un nouveau statut s'ajoute **là**, jamais dans
la page qui l'affiche. Le test `status-badge.test.tsx` parcourt `src/` et
échoue sur toute classe `text-<teinte>-NNN`, et sur `(bg|text|border|fill|
stroke|shadow)-(white|black)`.

Les **prédicats** de statut — brouillon, déclarée, constat manquant, clôturée,
pièce remplaçable — vivent dans `lib/circuit.ts`, pendant côté client de
`backend/core/statuts.py` ; les **teintes de carte** (ligne de dépense,
réallocation, flux) dans `status-styles.ts`. Un composant ne compare jamais
`x.status === "…"` lui-même : le même test échoue sur toute comparaison de ce
genre hors de `src/lib/`. Le niveau d'exécution d'une enveloppe (`ok`,
`warning`, `exceeded`) vient du serveur (`execution_level`) et se teinte par
`EXECUTION_LEVEL_TEXT` ; le client ne compare aucun taux à aucun seuil.

---

## Typographie

Police unique : **Geist Variable** (`--font-sans`), déjà chargée.

| Rôle | Classes |
|---|---|
| Titre de page | `text-2xl font-semibold tracking-tight` |
| Titre de section, de carte | `text-sm font-semibold` |
| Chiffre mis en avant | `text-2xl font-semibold tracking-tight` |
| Corps | `text-sm` |
| Légende, métadonnée | `text-xs text-muted-foreground` |
| Étiquette de colonne | `text-xs font-medium uppercase tracking-wider text-muted-foreground` |
| Empreinte, adresse IP, identifiant | ajouter `font-mono` |

Le titre de page passe par `<PageHeader>` : ne le réécrivez pas à la main.

---

## Espacement et rayons

- Rythme vertical d'une page : `space-y-6`. À l'intérieur d'une carte :
  `space-y-3`. Entre un libellé et son champ : `gap-2`.
- Grille de cartes : `grid gap-4 sm:grid-cols-2 lg:grid-cols-4`.
- Contenu de carte : `CardContent` avec `pt-6` quand il n'y a pas d'en-tête.
- Rayons dérivés de `--radius: 0.7rem` : `rounded-lg` pour les champs et
  boutons, `rounded-xl` pour les cartes, `rounded-2xl` pour les pastilles
  d'identité.

---

## Anatomie des composants

### Boutons

Variantes : `default` (action principale), `outline` (action secondaire),
`ghost` (action de ligne, souvent en icône), `destructive`, `secondary`,
`link`. Tailles : `xs`, `sm`, `default`, `lg`, `icon`.

- Une action principale par écran, en `default`.
- Une action de ligne de tableau est un `ghost` `icon` **avec `aria-label`**.
- Icône à gauche du libellé, `mr-1` en `sm`, `mr-2` sinon.
- Pendant une action : `<Loader2 className="animate-spin" />` à la place de
  l'icône, bouton `disabled`.

### Champs

`<Input>` et `<NativeSelect>` partagent la même hauteur et le même style.
Toujours un `<Label htmlFor>` associé. Le projet utilise **base-ui** sous
shadcn, dont l'API diffère de Radix : pour les listes déroulantes, préférez
`NativeSelect` — comportement clavier natif, rendu correct sur mobile.

### Tableaux

```tsx
<div className="overflow-hidden rounded-lg border border-border/60">
  <Table>…</Table>
</div>
```

- Montants alignés à droite ; un écart non nul en `text-destructive`.
- Deuxième ligne de contexte sous la valeur principale, en
  `text-xs text-muted-foreground`.
- Un tableau large va dans `overflow-x-auto` — jamais la page entière.
- Toujours paginé via `<Pagination>` dès qu'il peut dépasser une page.

### Dialogues

Titre affirmatif, description qui dit la conséquence. Actions en bas à droite :
`outline` pour annuler, puis l'action principale.

`DialogContent` **borne lui-même sa hauteur** (`max-h-[90vh] overflow-y-auto`) :
la règle a d'abord été confiée à l'appelant, et trois formulaires sur cinq
l'avaient oubliée. Un conteneur `fixed top-1/2 -translate-y-1/2` plus haut que
la fenêtre déborde des deux côtés sans que la page puisse défiler : à neuf
champs (797 px) sur un écran de 768 px, le bouton d'enregistrement devenait
inatteignable. Une page n'a plus à y penser.

### Graphiques

Un chiffre se lit ; une proportion se voit. Là où le lecteur cherche un
rapport — consommé contre enveloppe, justifié contre dépensé, un pays
contre les autres —, le graphique passe avant le tableau. Les primitives
vivent dans `components/ui/charts.tsx` ; n'en dessinez pas d'autres dans
une page.

| Primitive | Ce qu'elle montre | Où |
|---|---|---|
| `JaugeDouble` | Exécution et justification en deux anneaux, sur le bandeau marine | Pilotage |
| `Jauge` | Le taux d'une sous-enveloppe, teinté par le seuil franchi | Budgets |
| `CourbeMensuelle` | Dépensé en aire, justifié en pointillé, sur douze mois | Pilotage |
| `BarreEnveloppe` | Un pays contre son enveloppe, à échelle commune, dépassement en corail | Pilotage, Budgets |
| `RailEnveloppe` | Une enveloppe et ses seuils d'alerte gradués | Budgets |
| `BarreEcart` | La part justifiée d'une dépense, et son écart | Dossier — détail |
| `Legende` | Pastille et libellé d'une série ; `dashed` pour un repère en pointillé | toutes |

Trois règles s'y appliquent :

- **Elles ne calculent que des longueurs.** Largeur de barre, longueur
  d'arc, coordonnée d'un point : de la géométrie. Un taux affiché vient du
  serveur et passe par `formatRate` — jamais d'un `a / b` écrit dans la
  page. C'est la règle « rien ne se calcule dans l'interface », appliquée à
  la lettre : `ratio()` (`lib/utils.ts`) borne une part à son tout pour le
  dessin, et rien d'autre. L'échelle commune d'une liste de barres se prend
  à `echelleCommune()` (`lib/echelle.ts`) : le pilotage et les budgets la
  recopiaient mot pour mot, et le correctif qui y fait entrer l'engagé a dû
  l'être aussi. Un garde-fou tient la règle,
  `lib/rien-ne-se-calcule.test.ts` : il refuse qu'une page compose deux
  montants du serveur, et n'excepte que les deux fichiers qui dessinent.
- **Le dessin ne remplace pas les chiffres.** Chaque graphique est
  accompagné des montants en texte : la barre donne la forme, la ligne
  d'à côté donne les nombres. Le SVG lui-même est `aria-hidden` et porte
  son `title` en `sr-only` — un graphique n'est jamais la seule source
  d'une information.
- **Aucune couleur en dur.** Les séries prennent `marque`, `marque-clair`,
  `banniere-accent` ; l'écart et le dépassement prennent `destructive` ;
  le seuil d'alerte prend `statut-attente`.

### Filtres à bascule

`<FilterChips>` (`components/ui/filter-chips.tsx`) remplace une liste
déroulante quand les valeurs sont peu nombreuses et qu'on gagne à les voir
toutes — les six statuts du circuit, sur la liste des dossiers. Chaque
pastille est un `<button>` qui expose `aria-pressed`, dans un `<fieldset>`
dont la `<legend>` en `sr-only` dit ce qui est filtré. Au-delà de six ou
sept valeurs, revenez au `NativeSelect`.

---

## États

| État | Composant |
|---|---|
| Chargement d'un tableau | `<SkeletonRows columns={n} />` |
| Tableau vide | `<EmptyRow colSpan={n} icon={…} title="…" hint="…" />` |
| Erreur de page | `<Alert variant="destructive">` |
| Erreur de formulaire | `<FormError>{message}</FormError>` (`role="alert"`, ne rend rien sans message) |
| Erreur de rendu | `<ErrorBoundary>` autour du layout (`components/ui/error-boundary.tsx`) |
| Avertissement métier | `<Alert>` neutre |
| Indicateur chiffré | `<StatCard label value hint />` (`components/ui/stat-card.tsx`) ; `tone="danger"` pour un écart, `children` pour une barre sous le chiffre |
| Liste plafonnée par le serveur | `<TruncatedNotice page={…} noun={…} />` ; le composant se tait tant que la page n'est pas tronquée |
| Actualisation en arrière-plan | `<RefreshIndicator />` (`components/ui/refresh-indicator.tsx`) : `<output>`, icône `aria-hidden`, libellé `sr-only` — jamais un `aria-label` posé sur un `<svg>` sans rôle, que les lecteurs d'écran n'annoncent pas |

Le chargement des données passe par `useQuery(clé, fetcher)` (annulation de la
requête précédente, `loading` distinct de `refreshing`) et, pour les
pages de **détail** identifiées par l'URL, avec `keepPreviousData: false` :
sans elle, l'entité précédente restait affichée sous la nouvelle URL le temps
de la requête, et un clic créait une ligne dans le mauvais dossier. Une liste
filtrée garde au contraire ce qui est affiché. Un 503 ou un 429 porte
`ApiError.retryAfter` ; `useQuery` rejoue une fois, seul, après ce délai
(borné à 60 s). Le rafraîchissement du profil (`refreshProfile`) ne démonte
rien : `Protected` n'affiche le chargeur plein écran que tant qu'aucun profil
n'est connu. Pour les
référentiels, par `useReferentiel(clé, fetcher)` (cache mémoire cinq minutes,
`invalidateReferentiel` après une écriture). Les recherches sont différées par
`useDebouncedValue` (`lib/use-debounced.ts`). La remise à la première page se fait dans le gestionnaire du
filtre, jamais dans un effet.

Un état vide doit dire **quoi faire**, pas seulement constater le vide.
« Aucun dossier — Créez un dossier pour y rattacher vos dépenses » vaut mieux
que « Aucune donnée ».

---

## Droits et données

- Les droits viennent de `/api/me/` via `can("expenses.create")`,
  `can("expenses.validate")`, `can("audit.read")`… — les clés sont celles
  de la matrice (`accounts/permissions.py`), que les administrateurs règlent
  dans « Configuration › Permissions ». Sur un dossier ou une ligne, ce qui
  est possible vient de `allowed_actions` (`edit`, `add_line`, `upload`,
  `delete`, puis le circuit). **Ne recopiez jamais une table de rôles ni une
  liste d'états dans un composant** : elle divergerait du serveur. Masquer
  une action est un confort ; le refus reste côté serveur.
- **Aucune chaîne en dur visible par l'utilisateur.** L'interface est
  bilingue : tout texte passe par la fonction de traduction du projet
  (`t("…")`, dictionnaires français et anglais), y compris les `aria-label`,
  les états vides et les messages d'erreur construits côté client. Les
  libellés qui viennent du serveur (`*_display`, `detail`) arrivent déjà
  dans la langue de l'en-tête `Accept-Language`, que le client fixe d'après
  la préférence du profil : on les affiche tels quels. Le français est la
  langue de référence des clés.
- Les montants transitent en **chaîne** pour préserver la précision décimale.
  La conversion en `number` n'a lieu qu'au formatage.
- Formatage : `formatAmount`, `formatRate`, `formatDate`, `formatDateIn`.
- Les heures d'une dépense se lisent dans le **fuseau du pays**
  (`formatDateIn(date, country_timezone)`), pas dans celui du lecteur.

---

## Écrans et commandes imposés

Ces éléments relèvent des règles du produit, pas du goût : leur emplacement
et leur comportement sont fixés ici, et l'écran qui les porte doit s'y
conformer.

### Identité : logo, emblème, version

Le logo — l'emblème « J » en document coché, suivi du nom « JUSTI INNOV » —
est celui fourni par INNOV PHARMA (`docs/identite/logo-justi-innov.png`,
la source). Dans l'interface il n'existe qu'en vectoriel, tracé en
`currentColor` : `BrandLogo` (`components/layout/brand-logo.tsx`, emblème et
nom) et `BrandMark` (`brand-mark.tsx`, l'emblème seul). Il prend la couleur
du texte qui l'entoure, donc le thème — jamais une couleur en dur, jamais
une image PNG. Le logo complet va dans l'en-tête (`h-7`, lien vers
l'accueil) et sur l'écran de connexion (`h-9`, clair sur le panneau
sombre) ; l'emblème seul partout où 40 px ne suffiraient pas à lire le nom
(titre du panneau replié). Le nom fait partie du dessin : `BrandLogo` le
redit aux lecteurs d'écran par un texte masqué (`sr-only`), et il n'est
pas répété en texte visible à côté.

L'icône d'onglet et d'application installée (`public/favicon.svg`,
`favicon.png`, `public/icons/`) est l'emblème blanc sur un carré sombre à
coins arrondis, lisible sur une barre d'onglets claire comme sombre ; la
version « maskable » garde l'emblème dans la zone sûre.

La **version** (pied de page, pastille de l'en-tête, écran de connexion)
vient de `BRAND.version`, figée à la construction : celle du tag `v*`
livré, sinon celle de `package.json` (`vite.config.ts`, `define`). On ne
l'écrit nulle part ailleurs ; poser un tag suffit.

### Bouton « Retour »

En haut de chaque page sauf l'accueil, avant le `PageHeader` : un bouton
`ghost` de taille `sm`, icône `ArrowLeft`, libellé « Retour »
(`components/layout/back-button.tsx`, monté par `AppLayout`, masqué quand la
plateforme est fermée — mot de passe provisoire, enrôlement exigé). Il
revient à l'écran précédent quand la navigation a commencé dans
l'application, sinon à la liste de la section (`lib/navigation.ts`,
`parentPath` : `/dossiers/12` → `/dossiers`, `/dossiers` → `/`). Une page
ne rajoute pas son propre lien « Retour aux… » : il y en a un, au même
endroit partout.

### Sélecteur de langue

En haut à droite, à côté du sélecteur de thème et du menu du compte —
un bouton à icône propre (`language-toggle.tsx`), pas une entrée du menu :
un `DropdownMenuRadioGroup` avec deux choix, **Français** et **English**,
chacun écrit dans sa propre langue et porteur de son attribut `lang`. Le choix est enregistré sur
le profil (`PATCH /api/me/`, champ `language`) et appliqué sans
rechargement ; l'en-tête `Accept-Language` des requêtes suivantes le suit,
et les notifications comme les e-mails arrivent dans cette langue.
Avant la connexion, l'écran de connexion propose le même sélecteur, dont le
choix ne vaut que pour cet écran, puis s'efface devant la préférence du
profil. Les dates et les montants se formatent dans la langue choisie
(`formatDate`, `formatAmount` lisent la langue courante), la devise reste
celle du pays.

### Menu du compte

En haut à droite, à côté des sélecteurs de thème et de langue
(`user-menu.tsx`). Il porte, dans l'ordre : l'identité (`username ·
role_display`) avec une pastille **« 2FA active »** (`Badge`,
`STATUS_TONES.SUCCES`) quand `totp_confirmed` est vrai ; les équipes d'un
manager qui y est rattaché ; **« Activer la double authentification »**
(icône `ShieldCheck`, lien vers `/2fa`) tant que `totp_confirmed` est
faux — rien quand le serveur ne connaît pas la 2FA ; **« Supervision »**
(icône `Activity`) pour les administrateurs seulement
(`can("configuration.manage")`) **et** sur une pile qui l'expose
(`me.supervision`, d'après `DJANGO_SUPERVISION` : sans Grafana derrière
Caddy le lien mènerait à un 404), qui ouvre `/grafana/` — chemin relatif à l'origine, servi par Caddy — dans
un nouvel onglet avec `rel="noopener noreferrer"`, parce que Grafana a sa
propre session ; « Installer l'application » quand le navigateur le
permet ; « Déconnexion ». Les libellés de menu vivent dans un
`DropdownMenuGroup` : base-ui refuse un `DropdownMenuLabel` orphelin.

### Double authentification

Elle est **proposée, pas imposée** — décision reportée par la direction.
`GET /api/me/` porte la politique (`totp_required`, faux par défaut) et
l'état (`totp_confirmed`) ; `platformClosed` et `totpEnrolmentRequired`
(`lib/accounts.ts`) en tirent les conséquences, jamais une page.

- **Enrôlement** (`/2fa`, `totp-notice.tsx`, dans la même mise en page que
  l'écran du mot de passe provisoire) : `POST /api/me/2fa/enrol/` donne
  `qr_png_base64`, `otpauth_uri` et `secret` ; le QR au centre, le secret
  en clair dessous en `font-mono` avec un bouton « Copier » pour qui ne
  peut pas scanner, un champ « Code à six chiffres » (`inputMode="numeric"`,
  `autoComplete="one-time-code"`), un bouton principal « Confirmer »
  (`POST /api/me/2fa/confirm/ {code}`). Une phrase dit ce qu'il faut :
  « Scannez ce code avec votre application d'authentification, puis
  saisissez le code qu'elle affiche. » Le secret ne sera plus montré :
  l'écran le dit. On y vient de deux façons :
  - **volontairement**, par le menu du compte : `<Alert>` neutre
    « Activer la double authentification », bouton `outline` « Plus tard »
    qui ramène à l'accueil, navigation ordinaire autour ;
  - **imposé**, quand `totp_required` est vrai et le compte non enrôlé
    (première connexion, ou après réinitialisation par un administrateur —
    le serveur répond `403 {"totp_setup_required": true}` et le client y
    va comme il va à l'écran du mot de passe provisoire) : `<Alert>` en
    `statut-attente`, pas de « Plus tard », et la plateforme reste
    **fermée** — aucun menu — tant que l'écran n'est pas passé, après
    celui du mot de passe provisoire.
- **Vérification** (chaque connexion d'un compte enrôlé) : le champ
  « Code » est sur l'écran de connexion lui-même, toujours visible et
  **facultatif**, avec l'aide « Uniquement si vous avez activé la double
  authentification » — `POST /api/token-auth/` prend `{username, password,
  code}` et répond `400 totp_required` sans code valide à un compte
  enrôlé ; le champ devient alors exigé, sans perdre l'identifiant ni le
  mot de passe. Le bouton « Se connecter », et un repli
  `<details>` « Je n'ai plus accès à mon application » qui n'ouvre rien
  d'automatique : il explique que seul un administrateur peut réinitialiser
  l'enrôlement, et à qui s'adresser.

Un code refusé s'affiche en `<FormError>` sans vider le champ ; on ne
désactive pas le bouton pour un champ vide (règle d'accessibilité
ci-dessous). Aucune option « se souvenir de cet appareil » : le code est
demandé à chaque connexion d'un compte enrôlé.

### Le circuit en frise

Le détail d'un dossier ouvre sur `<FriseDuCircuit>`
(`components/expenses/workflow-frieze.tsx`), avant les chiffres : cinq
étapes — brouillon, soumis, en contrôle, justifié, clôturé — franchies,
courante ou à venir. L'ordre vient de `CIRCUIT` (`lib/labels.ts`), qui suit
`backend/core/statuts.py` ; il ne se recopie pas dans une page. Le constat
de non-justification **n'est pas une sixième étape** : il prend la place de
« justifié », en corail. La frise dit l'état et rien d'autre — les actions
restent celles d'`allowed_actions`, dans `PageHeader` et sur chaque ligne.
Elle n'affiche ni date ni auteur par étape : cela vit dans le journal
d'audit, réservé aux administrateurs, qu'un DF lisant cet écran n'a pas.

### Réouverture d'un dossier

Sur le détail d'un dossier, un bouton **« Rouvrir »** en variante
`outline`, dans les actions de `PageHeader`, rendu **seulement** si
`can("dossiers.reopen")` — `admin` et `super_admin` par défaut, jamais le
pays — et si le dossier est soumis, en contrôle ou non justifié
(`POST /api/dossiers/{id}/reopen/ {note}`). Il ouvre un
dialogue au titre affirmatif (« Rouvrir le dossier N°… »), dont la
description dit la conséquence : « Le dossier et ses lignes reviennent au
brouillon ; le pays est prévenu et devra le soumettre à nouveau. Le motif
est conservé dans le journal d'audit. » Le champ « Motif » (`note`) est
obligatoire et se valide à la soumission ; un refus du serveur parce
qu'une ligne est déjà justifiée (`400` sur `expenses`) s'affiche en
`<FormError>` dans le dialogue. Bouton principal « Rouvrir », en `default`,
pas en `destructive` : ce n'est pas une suppression.

Un dossier rouvert le montre : un `<Alert>` neutre en tête du détail,
« Rouvert — motif : … » (`reopen_note`), tant qu'il n'a pas été soumis à
nouveau ; et la ligne `reopened` figure dans le journal d'audit du dossier.
Quand une ligne est justifiée ou clôturée, le bouton n'apparaît pas : le
serveur refuserait, et un bouton qui mène à un refus n'a rien à faire à
l'écran.

### Rectification d'un constat

Là où la réouverture s'arrête — une ligne justifiée ou clôturée — commence
la rectification, en deux temps et à deux personnes. Sur chaque ligne du
détail d'un dossier, un bouton **« Rectifier »** (`outline`, icône
`Undo2`, `components/expenses/request-rectification.tsx`), à côté des
actions du circuit, rendu **seulement** si `allowed_actions` de la ligne
contient `request_rectification` — le serveur le dit : droit
(`rectifications.request`, tous les rôles par défaut), ligne justifiée ou
clôturée, aucune demande déjà en attente. Il ouvre un dialogue au titre
affirmatif (« Demander la rectification — Hôtel… »), dont la description
dit la conséquence : un administrateur décidera ; s'il approuve, la ligne
revient en contrôle, son montant justifié est remis à zéro et le siège
tranche à nouveau, le dossier la suit ; le motif est obligatoire et
conservé dans le journal. Champ « Motif » (`motif`), validé à la
soumission ; un refus du serveur sur la ligne (`400` sur `expense` ou
`status`) s'affiche en `<FormError>` dans le dialogue, un refus sur le
motif sous le champ. Bouton principal « Demander », en `default`.

Les demandes du dossier s'affichent dans une carte **« Demandes de
rectification »** (`components/expenses/rectification-panel.tsx`), entre
les lignes et les pièces, **seulement s'il y en a** : la ligne contestée,
le constat contesté (badge de l'état d'avant, `WORKFLOW_STYLE`, et le
montant justifié défait), le motif, le statut de la demande
(`RECTIFICATION_STYLE` : en attente `ATTENTE`, approuvée `SUCCES`,
refusée `DANGER`), la décision et son auteur. Deux boutons icône,
**Approuver** (`Check`, teinte succès) et **Refuser** (`X`, destructive),
rendus seulement si `can_decide` — calculé par le serveur : demande en
attente, rôle décideur (`rectifications.decide` : administrateurs, jamais
le pays), pas l'auteur de la demande. Approuver agit en un geste ;
refuser ouvre un dialogue au motif obligatoire, bouton `destructive`
« Refuser ». Après une décision, la page relit le dossier et ses lignes.
Dans le journal d'audit : `rectification_requested`, `rectified` (la
ligne, et le dossier qui la suit), `rectification_decided` ; dans les
notifications, l'icône `Undo2`.

### Menu d'export

Les exports et l'import sont réservés aux administrateurs : le menu
n'apparaît que si `can("data.export")`. C'est un `DropdownMenu` ouvert par
un bouton `outline` « Exporter » (icône `Download`) dans les actions de
`PageHeader` des écrans registre, dossiers et tableau de bord, avec :

- le **format** : Excel (`xlsx`), CSV (`csv`), Word (`docx`), PDF
  (`report.pdf`) ;
- la **période** : l'exercice (`year`) ou un mois (`month`, 1 à 12), et
  le pays (`country`), repris des filtres de l'écran (le menu ne redemande
  pas ce que l'écran sait déjà) ;
- une mention « Chaque export est inscrit au journal d'audit », en
  `text-xs text-muted-foreground`, parce que c'est vrai et que cela doit
  se savoir.

Le fichier se télécharge par la vue authentifiée (`/api/exports/…`), jamais
par une URL construite à la main ; pendant la génération, le bouton montre
`<Loader2 className="animate-spin" />`. Le registre porte le même menu, qui
reprend le pays de son filtre. L'import (`Upload`) vit dans l'onglet
« Import » de la Configuration (`?onglet=import`), réservé à
`can("data.import")`, et propose la simulation (`dry_run`) avant
l'écriture. Pour tous les autres rôles, ni bouton, ni lien : ils
travaillent dans l'application.

---

## Accessibilité

- Tout bouton à icône seule porte un `aria-label`.
- Un message d'erreur porte `role="alert"`.
- **Ne désactivez pas un bouton de soumission pour cause de champ vide** : il
  n'explique rien. Validez à la soumission et affichez la raison.
- Conservez l'anneau de focus sur tout élément interactif construit à la main.
- Libellés liés par `htmlFor` / `id`.
- Une ligne de tableau ne se clique pas : le nom ou le numéro est un `<Link>`,
  atteignable au clavier.
- Un choix exclusif dans un menu (thème) utilise `DropdownMenuRadioGroup`,
  qui expose `aria-checked`.
- Un champ de recherche sans libellé visible porte un `aria-label` ; un
  groupe de filtres à bascule expose `aria-pressed`.
- Le plugin `jsx-a11y` d'oxlint est actif : `npm run lint` refuse un bouton à
  icône sans libellé.

---

## Vérifier avant de conclure

```bash
cd frontend
npx tsc -b && npm run lint && npm run test

SHOT_HQ_USER=… SHOT_HQ_PASSWORD=… SHOT_HQ_TOTP_SECRET=… \
SHOT_COUNTRY_USER=… SHOT_COUNTRY_PASSWORD=… SHOT_COUNTRY_TOTP_SECRET=… \
npx tsx scripts/screenshot.ts     # parcours complet, siège et pays
npx tsx scripts/shot-login.ts     # connexion, grand écran et mobile
npx tsx scripts/shot-theme.mts    # écrans principaux, thème clair puis sombre
```

Les trois scripts **échouent si la console du navigateur a produit la moindre
erreur**. Regardez les captures : plusieurs défauts de ce projet — un
`method-wrapper` affiché en clair, une page qui plantait, un bouton d'édition
jamais rendu — n'ont été trouvés que là. Le compte siège utilisé ne doit pas
avoir de mot de passe provisoire (`must_change_password: false`), sans quoi
la plateforme fermée ne montre que l'écran de changement de mot de passe.
`SHOT_*_TOTP_SECRET` ne sert qu'à un compte enrôlé ; le parcours du siège
attend la pastille « 2FA active », donc un compte siège enrôlé. Le menu du
compte ne s'ouvre pas dans jsdom (base-ui) : c'est ce parcours qui le
vérifie.
`SHOT_BASE` (défaut `http://localhost:5173`) et `SHOT_OUT` (défaut `/tmp`)
ciblent une autre pile ou un autre dossier ; la CI les pointe sur la pile
livrable, port 8080.

---

## Points connus

- L'application est installable comme application de bureau (PWA) :
  manifeste et service worker viennent du build Vite, l'icône et le nom
  « JUSTI INNOV » y sont fixés. Le service worker ne met en cache que les
  fichiers statiques du build, jamais une réponse de `/api/` : un chiffre
  périmé affiché hors ligne serait pire qu'une page vide.
- Le sélecteur de thème propose « Clair », « Sombre » et « Système ». Le choix
  est local au navigateur et le script anti-flash `public/theme-init.js`,
  chargé par `index.html`, pose la classe `.dark` avant le montage de React ;
  `ThemeProvider` suit ensuite les changements de préférence du système. Le
  script est un **fichier**, pas un bloc `<script>` en ligne : la politique
  de sécurité de contenu de `frontend/nginx.conf` n'autorise que
  `script-src 'self'`, et un bloc en ligne serait bloqué en production sans
  rien casser en développement.
- **`PageHeader` (`components/ui/page-header.tsx`) est obligatoire sur toute
  page** : titre, description et actions y prennent la même place partout.
  Une page qui compose son propre en-tête rompt cet alignement ; ajoutez
  une option au composant plutôt qu'une exception dans la page.
