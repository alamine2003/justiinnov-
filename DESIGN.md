# DESIGN.md — système d'interface de JUSTI GH

> Référence unique de l'interface. **À lire avant toute modification d'écran.**
> Les tokens vivent dans `frontend/src/index.css` ; ce document dit comment
> s'en servir.

L'application sert le siège — l'administrateur (RH), qui contrôle, et la
direction, qui supervise — et les managers des filiales, qui déclarent, qui lisent des chiffres et cherchent des preuves, sur un poste de
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

Le logo a ses propres couleurs — bleu, rouge et orange de Generic
Healthcare (`--logo`, `--logo-rouge`, `--logo-orange`) — qui ne servent
qu'à lui (« Identité », plus bas).

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

- Rythme vertical d'une page : `space-y-6`, `court:space-y-3` sur écran
  bas (voir « Hauteur d'écran »). À l'intérieur d'une carte :
  `space-y-3`. Entre un libellé et son champ : `gap-2`.
- Grille de cartes : `grid gap-4 sm:grid-cols-2 lg:grid-cols-4`.
- Contenu de carte : `CardContent` **sans** marge haute ajoutée — la carte a
  déjà la sienne (`py-(--card-spacing)`, 16 px). Un `pt-6` de plus laissait
  40 px vides au-dessus des tableaux et 16 en dessous.
- Rayons dérivés de `--radius: 0.7rem` : `rounded-lg` pour les champs et
  boutons, `rounded-xl` pour les cartes, `rounded-2xl` pour les pastilles
  d'identité.

### Largeurs d'écran

Le poste de travail d'abord, mais rien ne casse de 1 440 px à un
téléphone : **aucune page ne défile horizontalement** — seul un tableau ou
un graphique défile, dans sa propre boîte.

- **Navigation** (`AppLayout`) : barre latérale dès `lg` (1 024 px), menu ☰
  et panneau en dessous — voir « Navigation » ci-dessous. La barre du haut
  qui la précédait demandait 1 280 px pour les sept entrées du siège ; à
  768 px, la page débordait de 163 px.
- **Onglets qui passent à la ligne** (`TabsList` avec `flex-wrap`) : la
  liste a une hauteur *minimale*, jamais fixe — sans quoi la seconde ligne
  recouvre le contenu qui suit.
- **Graphiques** (`CourbeMensuelle`, `BarresParJour`) : largeur minimale de
  50 rem et défilement dans leur boîte ; leur texte est en unités du dessin
  (11 sur 1 000 : 9 px au plus étroit, 13 px sur une carte de bureau), qu'une
  réduction rendrait illisible et qu'un agrandissement rendrait énorme.
- **Frise du circuit** : 56 px par étape sous `sm`, 112 au-delà.
- **Grand écran** : le contenu s'élargit à `2xl:max-w-[96rem]` (1 536 px),
  `max-w-7xl` en dessous ; au-delà, les lignes de chiffres se liraient de
  trop loin.

### Hauteur d'écran

Dès `lg`, **les écrans principaux tiennent dans la fenêtre** : la page ne
défile pas, c'est son tableau ou son détail qui défile, dans sa boîte, sous
un en-tête et des filtres qui restent en vue. Ce sont Pilotage, Projets et
la fiche d'un projet, Dossiers et la fiche d'un dossier, Registre, Audit,
Budgets et Configuration.
`scripts/screenshot.ts` le vérifie à 1 366 × 768, 1 366 × 657 (le même
portable, barre du navigateur déduite), 1 024 × 768 et 1 920 × 1 080. La
fiche d'un pays et l'import, formulaires et détails longs, gardent le
défilement de page. Sous `lg`, et sous 36 rem (576 px)
de fenêtre, la page défile normalement : le contenu y déborderait de
boîtes plafonnées, hors du cadre de sa carte, et la barre latérale partirait
avec le défilement.

- **`--hauteur-page`**, posée sur `<main>` par `AppLayout` : la fenêtre
  moins l'en-tête et les marges de `<main>` (`calc(100dvh - 7rem - 1px)`,
  6 rem sur écran bas ; le pixel est le filet de l'en-tête), moins la
  ligne du bouton « Retour » quand il s'affiche (`--retour`, 2,75 rem,
  2,25 sur écran bas). On ne la recalcule pas dans une page : on la lit.
  L'avis d'une redirection (« réservée au siège »), ponctuel, n'est pas
  retranché : la page défile alors de sa hauteur.
- **Variante `court:`** (`index.css`, `max-height: 860px` — un portable
  1 366 × 768) : l'espace vertical se resserre — `court:space-y-3` au lieu
  de `space-y-6` à la racine d'une page, titre de page en `text-xl`, tuiles
  (`StatCard`) en 12 px de marge et chiffre en `text-xl`, bandeau et jauge
  du pilotage réduits. On resserre l'espace, jamais le texte courant ni les
  cibles cliquables.
- **Une liste** : trois utilitaires de `index.css`, sans rien d'autre à
  écrire —
  ```tsx
  <div className="ecran-plein space-y-6 court:space-y-3">  {/* racine */}
    <PageHeader … />  {/* filtres, alertes : ne rétrécissent pas */}
    <Card className="remplit …">
      <CardContent className="remplit">
        <div className="defile overflow-x-auto rounded-lg border …"><Table>…</Table></div>
        <Pagination … />
      </CardContent>
    </Card>
  </div>
  ```
  `ecran-plein` plafonne la racine à `--hauteur-page` ; `remplit` va sur
  **chaque** conteneur entre elle et le tableau (onglets compris) ;
  `defile` fait défiler l'enveloppe du tableau et colle ses titres de
  colonnes en haut. Une liste courte garde sa hauteur naturelle ; sous
  8 rem de tableau, c'est la page qui défile, et la carte qui `remplit` ne
  rogne pas sa pagination (`overflow: visible`). Les autres enfants ne
  rétrécissent jamais — une carte, `overflow-hidden`, s'écrasait sous son
  contenu (les filtres du registre l'ont fait).
- **Un tableau de bord long** (vue d'ensemble de l'audit, budgets,
  sections de la configuration, historique d'un projet, lignes d'un dossier
  et leur rail) : ce qui situe
  (en-tête, période, indicateurs, onglets) reste en vue, le reste va dans
  un `defile -mx-1 px-1 pb-1` — la marge rend aux cartes l'ombre et
  l'anneau de focus que le défilement rognerait.
- **Pilotage** remplit exactement la fenêtre (`lg:h-(--hauteur-page)`,
  plancher 34 rem) : bandeau et tuiles en haut, puis deux panneaux côte à
  côte qui défilent chacun — l'analyse (onglets Mois · Répartition · Pays ;
  la répartition se lit un axe à la fois, choisi dans une liste) ou la
  liste des pays, et les alertes.
- **Une zone qui défile est positionnée** (`relative`, que `defile` pose) :
  un `sr-only`, en position absolue, s'échappe sinon d'un `overflow-auto`
  non positionné et rallonge la page — 54 px sur le pilotage.
- **Le pied de page** passe dans le bas de la barre latérale dès `lg`
  (copyright, version, auteur ; la version seule quand elle est repliée) :
  sous le contenu, il ne se voyait qu'en défilant. Sous `lg`, il reste
  sous le contenu.
- **Le bouton « Retour »** ne s'affiche pas, dès `lg`, sur une entrée du
  menu : la barre latérale y mène déjà (voir « Bouton « Retour » »).

### Navigation

`AppLayout` (`components/layout/app-layout.tsx`) range les entrées dans une
**barre latérale** dès `lg`, par groupe : **Suivi** (Pilotage, Projets,
Registre), **Budget** (Budgets, Pays), **Contrôle** (Audit, si
`can("audit.read")`), **Administration** (Configuration, si
`can("configuration.manage")`). Un groupe que les droits laissent vide ne
s'affiche pas. Surface neutre (`bg-card`, `border-r border-border/60`),
entrée active en `bg-accent` : la barre ne porte aucune teinte de marque.

- **Repliable** en bande d'icônes de 4 rem (bouton « Réduire le menu », en
  bas, `aria-expanded`) : les libellés passent en `sr-only` — ils restent
  le nom accessible — et en info-bulle, les intitulés de groupe en filet.
  Le choix est propre au navigateur (`localStorage`, `justi_menu_replie`,
  lu et écrit sous `try/catch`) ; par défaut, la barre est dépliée.
- **L'en-tête** garde à gauche le **périmètre** (« Siège — tous pays »,
  « TG-01 ») — il dit quelles données on lit — et à droite la cloche, la
  langue, le thème et le menu du compte. Sous `lg`, il reprend le logo et
  le menu ☰, qui ouvre la même navigation groupée dans un panneau.
- Le repère s'appelle toujours « Navigation principale » : les captures
  (`scripts/screenshot.ts`) et la CI comptent ses liens.
- Plateforme fermée (mot de passe provisoire, enrôlement exigé) : pas de
  barre latérale, le logo reste dans l'en-tête.

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
- Dans une liste à hauteur d'écran, l'enveloppe porte `defile` : voir
  « Hauteur d'écran ».

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
| `BarresParJour` | Événements par jour, circuit en `marque`, référentiel en `marque-clair`, empilés | Audit — vue d'ensemble |
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

Le logo est celui de **Generic Healthcare** (décision 92) : « JUSTI »
écrit, suivi du monogramme « GH », ce qui se lit « JUSTI GH » sans
répéter « GH ». Le monogramme est vectorisé depuis le fichier fourni
(`docs/identite/logo-gh.png`, 109 × 120 pixels, flou) : chaque couleur
séparée, son contour lissé puis tracé en courbes
(`docs/identite/logo-gh.svg`). Le mot n'est pas tracé mais écrit, en
`<text>` dans le même SVG, à largeur fixée (`textLength`) pour garder les
proportions quelle que soit la police. Dans l'interface le logo n'existe
qu'en vectoriel, jamais en image PNG : `BrandLogo`
(`components/layout/brand-logo.tsx`, mot et monogramme) et `BrandMark`
(`brand-mark.tsx`, le monogramme seul).

Il garde ses trois couleurs, par des jetons réservés au logo : le bleu
(`text-logo`, porté par le mot et le monogramme, en `currentColor`), le
rouge et l'orange des deux traits (`fill-logo-rouge`, `fill-logo-orange`).
Le bleu du groupe se perd sur fond sombre : en thème sombre, `--logo`
prend la couleur du texte ; sur le panneau marine de la connexion, l'écran
passe `text-banniere-foreground`. Le rouge et l'orange ne changent pas.
Ces trois couleurs ne servent **qu'au logo** : ni surface, ni texte, ni
chiffre (« Couleurs de la marque », plus haut).

Le logo complet va dans l'en-tête (`h-7`, lien vers l'accueil) et sur
l'écran de connexion (`h-9`) ; le monogramme seul partout où 40 px ne
suffiraient pas à lire le mot (titre du panneau replié). Le nom fait partie
du dessin : `BrandLogo` le redit aux lecteurs d'écran par un texte masqué
(`sr-only`), et il n'est pas répété en texte visible à côté.

L'icône d'onglet et d'application installée (`public/favicon.svg`,
`favicon.png`, `public/icons/`) est le monogramme dans ses couleurs sur un
carré blanc à coins arrondis, lisible sur une barre d'onglets claire comme
sombre ; la version « maskable » garde le monogramme dans la zone sûre.
La tuile vectorielle `favicon.svg` fait foi : les PNG s'en déduisent par
`npx tsx scripts/generate-icons.mts` (dans `frontend/`).

La **version** (pied de la barre latérale dès `lg`, pied de page en
dessous, pastille de l'en-tête, écran de connexion)
vient de `BRAND.version`, figée à la construction (`vite.config.ts`,
`define`) : `APP_VERSION`, que la livraison pose à la version de
`package.json`, seule, sans SHA (décision 98). On ne
l'écrit nulle part ailleurs. Pour une nouvelle version, on relève
`package.json` (`npm version X.Y.Z --no-git-tag-version`), on fusionne,
puis on tague ce commit ; la livraison refuse un tag `vX.Y.Z` que
`package.json` ne porte pas (décision 98).

### Bouton « Retour »

En haut de chaque page sauf l'accueil, avant le `PageHeader` : un bouton
`ghost` de taille `sm`, icône `ArrowLeft`, libellé « Retour »
(`components/layout/back-button.tsx`, monté par `AppLayout`, masqué quand la
plateforme est fermée — mot de passe provisoire, enrôlement exigé). Il
revient à l'écran précédent quand la navigation a commencé dans
l'application, sinon à la liste de la section (`lib/navigation.ts`,
`parentPath` : `/projets/12` → `/projets`, `/projets` → `/`). Un dossier
ouvert d'un lien direct revient à `/dossiers` ; son fil d'Ariane mène à
son projet. Une page
ne rajoute pas son propre lien « Retour aux… » : il y en a un, au même
endroit partout. Dès `lg`, il se tait sur une entrée du menu (`/registre`,
`/audit`…, celles qu'`AppLayout` affiche au compte, `dansLeMenu`) — la
barre latérale, toujours visible, fait le même chemin et la ligne revient
au contenu. Il reste partout ailleurs : sur les fiches, sur `/dossiers`
(que le menu ne propose plus), et sous `lg`, où le menu est replié dans ☰.

### Sélecteur de langue

En haut à droite, à côté du sélecteur de thème et du menu du compte —
un bouton à icône propre (`language-toggle.tsx`), pas une entrée du menu :
un `DropdownMenuRadioGroup` avec deux choix, **Français** et **English**.
Le bouton montre l'icône et le code de la langue courante (« FR », « EN »),
l'icône seule se reconnaissant mal ; son nom accessible reste « Langue de
l'interface ». Les deux choix sont écrits chacun dans sa propre langue et porteur de son attribut `lang`. Le choix est enregistré sur
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
- **Vérification** (chaque connexion d'un compte enrôlé) : **en deux
  temps**. L'écran de connexion ne demande d'abord que l'identifiant et le
  mot de passe ; `POST /api/token-auth/` prend `{username, password, code}`
  et répond `400 totp_required` à un compte enrôlé sans code valide — après
  avoir vérifié le mot de passe. Le champ « Code » n'apparaît qu'alors,
  exigé et avec le focus, sous l'aide « Mot de passe accepté. Saisissez le
  code… », sans perdre l'identifiant ni le mot de passe ; un autre
  identifiant repart du premier temps. Montré à tous, le champ laissait
  croire à un compte non enrôlé qu'il lui manquait quelque chose (audit UX
  du 4 octobre 2026). Sous le champ, un repli `<details>` « Je n'ai plus
  accès à mon application » qui n'ouvre rien d'automatique : il explique
  que seul un administrateur peut réinitialiser l'enrôlement, et à qui
  s'adresser.
- **L'écran de connexion** ne présente que ce qui sert à entrer : l'aide
  utile à la tâche en `text-sm` (code, « Mot de passe oublié ? »), les
  mentions secondaires en `text-xs` ; l'installation de l'application se
  propose après la connexion, dans le menu du compte.

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
d'audit, réservé aux administrateurs, qu'un manager lisant cet écran n'a pas.

### Réouverture d'un dossier

Sur le détail d'un dossier, un bouton **« Rouvrir »** en variante
`outline`, dans les actions de `PageHeader`, rendu **seulement** si
`can("dossiers.reopen")` — l'`admin` seul, jamais le pays ni le
`super_admin` (décision 89) — et si le dossier est soumis, en contrôle ou non justifié
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
(`rectifications.request`, pays et super administrateur par défaut), ligne justifiée ou
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
le pays ni le `super_admin`), pas l'auteur de la demande. Approuver agit en un geste ;
refuser ouvre un dialogue au motif obligatoire, bouton `destructive`
« Refuser ». Après une décision, la page relit le dossier et ses lignes.
Dans le journal d'audit : `rectification_requested`, `rectified` (la
ligne, et le dossier qui la suit), `rectification_decided` ; dans les
notifications, l'icône `Undo2`.

### Supprimer une enveloppe

Sur la page Budgets, l'enveloppe du pays et chaque sous-enveloppe portent
un bouton icône **Supprimer** (`ghost`, `Trash2`, `text-destructive`,
`components/budgets/supprimer-enveloppe.tsx`), à côté du crayon, rendu
**seulement** si `can_delete` — le serveur le dit : droit
(`budgets.delete`, le super administrateur seul) et enveloppe jamais
servie (aucune dépense imputée, aucune réallocation, aucune
sous-enveloppe ; décision 91). Il ouvre un dialogue au titre en question
(« Supprimer « Équipe Lomé » (2027) ? »), dont la description dit la
conséquence : l'enveloppe disparaît, l'historique garde qui l'a supprimée,
une enveloppe qui a servi se désactive au lieu de se supprimer. Boutons
« Annuler » (`outline`) et « Supprimer » (`destructive`). Un refus du
serveur (une dépense imputée entre-temps, `400` sur `budget`) s'affiche en
`<FormError>` dans le dialogue, qui reste ouvert. Après une suppression, la
page relit les enveloppes.

### Bénéficiaires : contact à compléter

Dans l'onglet « Bénéficiaires » d'un pays, la colonne « Contact » montre le
téléphone et l'e-mail, séparés par « · ». Un bénéficiaire sans l'un ni
l'autre — saisi avant la décision 93 — porte un badge **« À compléter »**
(`STATUS_TONES.ATTENTE`), lu sur `contact_manquant` : l'écran ne le déduit
pas. Dans le formulaire, « Téléphone » (`type="tel"`) et « E-mail »
(`type="email"`) portent la mention « (l'un des deux) » au lieu de
« (facultatif) » (`FormField.mention` de `ManageRows`) ; la règle est
tranchée par le serveur, dont le refus s'affiche en un seul message en tête
du dialogue.

### Menu d'export

Les exports sont réservés aux administrateurs : le menu n'apparaît que si
`can("data.export")`. C'est un `DropdownMenu` ouvert par
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
reprend le pays de son filtre, comme la liste des dossiers. Pour tous les
autres rôles, ni bouton, ni lien : ils travaillent dans l'application.

### Import d'un classeur

Importer, c'est déclarer (décision 89) : l'import revient au pays et vit
avec les dossiers, pas dans la Configuration. Sur la fiche d'un projet qui
accepte des dossiers, et sur la liste des dossiers, un bouton `outline`
« Importer » (icône `Upload`), rendu seulement si `can("data.import")`,
mène à la page `/dossiers/import` — une page à part, avec son `PageHeader`
et le bouton « Retour » commun ; depuis un projet, `?project=` l'y choisit
d'avance. Un classeur s'importe dans un **projet** et sous un **type de
dossier** (décision 102) : deux `NativeSelect`, le second ne listant que
les types du type du projet ; le pays est celui du projet. Elle propose la
simulation (`dry_run`) avant l'écriture ; les erreurs se lisent au numéro
de ligne du classeur. Le siège ne voit pas le bouton. Depuis la décision
106, l'import n'ouvre plus de dossier : les lignes se versent dans le
dossier prédéfini du type choisi, et le résultat compte les lignes,
équipes et managers créés — plus de dossiers.

### Projets, la rubrique principale

Depuis la 2.0 (décisions 100 et 105), la navigation porte **« Projets »**
(icône `Briefcase`) à la place de « Dossiers » : Pays › Projet › Dossier ›
Lignes.

- **Liste** (`/projets`) : onglets par pays (`<CountryTabs>`,
  `components/countries/country-tabs.tsx`, partagé avec la liste des
  dossiers), recherche, puis le type de projet en `<FilterChips>`. Le nom
  est le lien, la référence (`TG-P-2026-001`) dessous en `font-mono
  text-xs`. Le type se lit par `<ProjectKindBadge>`
  (`status-badge.tsx`) : contourné (`outline`) pour un type, puisque ce
  n'est pas un état ; **« À typer »** (`ATTENTE`) pour un projet d'avant la
  2.0, **« Historique »** (`ARCHIVE`) pour le projet où la reprise a rangé
  les anciens dossiers — lus sur `a_typer` et `is_historical`.
  « Nouveau projet » (`default`) si `can("projets.create")` — le pays
  seul : pays (choisi d'office s'il n'y en a qu'un), nom, type, équipe
  (exigée d'un manager rattaché à des équipes), description. Le type
  choisi, le texte d'aide **annonce les dossiers que le projet recevra**,
  lus dans la liste commune du serveur (« Le projet recevra ses dossiers :
  Stands, T-shirts… ») — jamais recopiés dans l'interface. Un refus du
  serveur sur le type, l'équipe ou le nom s'écrit sous le champ ; le reste
  en `<FormError>`. La fiche du projet créé s'ouvre.
- **Fiche** (`/projets/:id`) : `PageHeader` au nom du projet, badges du
  type et du statut, référence et pays. Deux onglets `line` (`?onglet=`) :
  - **Dossiers** : ses dossiers prédéfinis dans
    `<DossiersTable colonne="type">` (`components/expenses/dossiers-table.tsx`,
    partagé avec `/dossiers`, où la colonne dit le projet), filtrables par
    type de dossier en pastilles (`?type=`). **Il n'y a pas de « Nouveau
    dossier »** : un projet naît avec les siens (décision 106), on les
    remplit. « Importer » ne s'affiche que si `accepte_des_dossiers` ;
    sinon un `<Alert>` neutre dit pourquoi (projet historique, à typer,
    désactivé) — plutôt qu'un bouton absent sans explication ;
  - **Historique**, si `can("audit.read")` (décision 110) : une chronologie
    de cartes `<Evenement>` (`components/audit/evenement.tsx`, partagée
    avec l'audit) — action, source, objet (lien vers un dossier), motif en
    tête, note, avant / après par `DiffList`, date, auteur, adresse ; un
    `<Alert>` renvoie au journal complet filtré par projet quand la liste
    est tronquée.
- **Actions du projet**, dans le `PageHeader` (`components/projects/`), chacune
  selon son droit, jamais selon le rôle :
  - **Renommer** (`outline`, `PencilLine`, `projets.rename` — le pays) :
    titre et **motif obligatoire** (`ChampMotif`), décision 109 ;
  - **Modifier** (`outline`, `Settings2`, `projets.update` — le siège) :
    statut, budget, description, activité, et le type d'un projet « à
    typer » ; **jamais le titre** ; motif obligatoire ;
  - **Compléter les dossiers** (`outline`, `FolderPlus`, `projets.update`,
    si `accepte_des_dossiers`) : confirmation, puis le serveur ouvre les
    dossiers prédéfinis qui manquent.
  Un refus du serveur s'affiche en `<FormError>`, dialogue ouvert.
- `/dossiers` reste — tuiles du pilotage (`?status=`), recherche
  transverse, export — mais quitte la navigation et n'ouvre plus de
  dossier.
- **Configuration › Types de dossiers** : la liste commune, en
  `ManageRows` ; en écriture seulement avec `can("dossier_kinds.manage")`
  (le super administrateur), en lecture pour la RH ; un type s'ajoute ou se
  désactive, avec un motif pour toute modification.
- Fiche d'un pays, onglet Projets : en **lecture seule** — nom en lien vers
  la fiche, référence, `<ProjectKindBadge>`. On crée, renomme, modifie et
  complète un projet depuis sa fiche, motif à l'appui.

### Fiche d'un dossier : fil d'Ariane et renommage

Au-dessus du `PageHeader`, un fil d'Ariane `nav` (`aria-label` « Fil
d'Ariane ») en `text-xs text-muted-foreground` : **Projets › projet ›
numéro**, les deux premiers en liens, le dernier `aria-current="page"` en
`font-mono`. Il complète le bouton « Retour », il ne le remplace pas. Le
titre de la page est le **titre** du dossier ; le numéro et le type
suivent dans la description.

Un bouton **« Renommer »** (`outline`, icône `PencilLine`,
`components/expenses/rename-dossier.tsx`), dans les actions du
`PageHeader`, rendu **seulement** si `allowed_actions` contient `rename`
(décisions 104 et 108 : un manager du pays, jusqu'à la clôture).

**Chaque ligne porte sa pièce** (décision 107). Sur la carte d'une ligne
(`CarteDeLigne`), sous la barre justifié / écart, un bloc « Justificatif » :
l'état se lit sur `has_proof`, dit par le serveur — « Sans justificatif »
en `statut-attente` (icône `FileWarning`) sinon —, puis les pièces de la
ligne en liste serrée (`<ProofPanel compact>`) : nom, version, badge de
statut, Aperçu, Télécharger, Contrôler selon `allowed_reviews`. « Déposer »
(`outline`, `sm`) n'apparaît que si la ligne porte `upload` ; le dépôt
envoie `expense`, jamais `dossier`, et le remplacement ne propose que les
pièces de la ligne. Le rail de droite ne garde que le nombre de lignes sans
justificatif (`lignes_sans_preuve`, un `<Alert>` neutre) et, s'il y en a,
les **pièces d'avant la 2.0**, déposées sur tout le dossier : elles se lisent
et se contrôlent, il ne s'en dépose plus.

### Audit en tableau de bord

La page Audit (`audit.read`, décision 111) porte trois onglets `line`
(`?onglet=`), et ses filtres vivent dans l'URL — période (`debut`, `fin`)
et pays, communs aux trois, puis ceux de chaque onglet : une tuile mène
au journal déjà filtré, et l'adresse se partage.

- **Vue d'ensemble** (`pages/audit/overview.tsx`), lue sur
  `/api/audit/synthese/` : une phrase de période avec les totaux du
  serveur ; deux rangées de `StatCard` — circuit, puis référentiel et
  comptes —, chacune un lien vers le journal filtré **quand un filtre
  reproduit exactement son compte**, sur la période que le serveur a
  comptée (« Lignes tranchées », « Refus », « Justificatifs déposés »
  réunissent plusieurs actions : pas de lien), bordée `danger`
  quand un compteur sensible (réouvertures, refus, retraits, sorties,
  échecs de connexion, droits…) n'est pas nul ; l'activité par jour en
  `BarresParJour` avec sa `Legende` et les chiffres jour par jour en texte
  (`<details>`) ; les plus actifs et l'activité par pays en tableaux ; la
  liste **« À surveiller »** en cartes `<Evenement>`. La page ne compte
  rien.
- **Circuit** : le journal d'audit, filtrable par action (renommage
  compris), objet, utilisateur et projet (`?projet=`, posé par
  l'historique d'un projet) ; un filtre posé par lien se retire par une
  pastille.
- **Référentiel et comptes** : l'historique (`/api/history/`), filtrable
  par action et par entité, recherche sur le motif comprise ; colonne
  « Motif » et avant / après par `DiffList`.
Dialogue « Renommer le dossier N°… », dont la description dit que seul le
titre change et que l'ancien reste au journal d'audit ; le champ part du
titre actuel. Un titre vide se refuse à la soumission ; un refus du
serveur s'affiche en `<FormError>`, dialogue ouvert.

Le formulaire de ligne ne propose plus de projet : la ligne suit celui de
son dossier. Seul un dossier du projet « Historique »
(`project_is_historical`) garde le choix, ses lignes portant chacune le
leur.

### Onglets par pays des dossiers et des projets

Un dossier appartient à un pays (décision 89). Dès que le compte voit
plusieurs pays — le siège, ou un manager rattaché à plusieurs pays —, la
liste des dossiers se sépare en **onglets**, au-dessus de la recherche :
« Tous les pays », puis un onglet par pays, chacun suivi du nombre de
dossiers qu'il affichera (décision 99). Un manager d'un seul pays n'en a
pas. La liste des projets a les mêmes, comptés par
`GET /api/projects/par-pays/`, par le même composant (`<CountryTabs>`).
Les onglets sont `Tabs` en variante `line`, qui passent à la ligne
quand les dix-sept filiales sont ouvertes — jamais une barre qui défile.
Les pays et leurs comptes viennent de `GET /api/dossiers/par-pays/`, avec
les filtres de la liste (statut, recherche) sauf le pays : l'interface ne
compte rien. Le pays vit dans l'URL (`?country=`), comme le statut, et part
aussi au menu d'export.

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
erreur** — une seule exception, nommée : le `400 totp_required` du premier
temps d'une connexion enrôlée (`POST /api/token-auth/`), voulu, que
`estLeRefusAttenduDuCode` (`scripts/login.ts`) écarte. Regardez les captures : plusieurs défauts de ce projet — un
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
  « JUSTI GH » y sont fixés. Le service worker ne met en cache que les
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
