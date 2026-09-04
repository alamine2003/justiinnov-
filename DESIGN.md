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

Palette **monochrome**, définie en `oklch` dans `frontend/src/index.css`, avec
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

`text-white` est proscrit sur un fond destructif : le jeton
`--destructive-foreground` garantit le contraste dans les deux thèmes.

Les teintes sont centralisées dans `lib/status-styles.ts`, les badges dans
`components/expenses/status-badge.tsx` (`StatusBadge`, `ProofStatusBadge`,
`ProjectStatusBadge`, libellé serveur `*_display` prioritaire) et les tables
`*_LABELS` dans `lib/labels.ts`, traduites dans les deux langues. Un nouveau statut s'ajoute **là**, jamais dans
la page qui l'affiche. Le test `status-badge.test.tsx` parcourt `src/` et
échoue sur toute classe `text-<teinte>-NNN` ou `text-white`.

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
`outline` pour annuler, puis l'action principale. Un formulaire long prend
`max-h-[90vh] overflow-y-auto`.

---

## États

| État | Composant |
|---|---|
| Chargement d'un tableau | `<SkeletonRows columns={n} />` |
| Tableau vide | `<EmptyRow colSpan={n} icon={…} title="…" hint="…" />` |
| Erreur de page | `<Alert variant="destructive">` |
| Erreur de formulaire | `<FormError message={…} />` (`role="alert"`) |
| Erreur de rendu | `<ErrorBoundary>` autour du layout (`components/ui/error-boundary.tsx`) |
| Avertissement métier | `<Alert>` neutre |
| Indicateur chiffré | `<StatCard label value hint />` (`components/ui/stat-card.tsx`) |
| Liste plafonnée par le serveur | `<TruncatedNotice count shown />` dès que `count > results.length` |

Le chargement des données passe par `useQuery(clé, fetcher)` (annulation de la
requête précédente, `loading` distinct de `refreshing`) et, pour les
référentiels, par `useReferentiel(clé, fetcher)` (cache mémoire cinq minutes,
`invalidateReferentiel` après une écriture). Les recherches sont différées par
`useDebounced`. La remise à la première page se fait dans le gestionnaire du
filtre, jamais dans un effet.

Un état vide doit dire **quoi faire**, pas seulement constater le vide.
« Aucun dossier — Créez un dossier pour y rattacher vos dépenses » vaut mieux
que « Aucune donnée ».

---

## Droits et données

- Les droits viennent de `/api/me/` via `can("record_expenses")`,
  `can("validate_expenses")`, `can("view_audit")`… **Ne recopiez jamais une
  table de rôles dans un composant** : elle divergerait du serveur. Masquer une
  action est un confort ; le refus reste côté serveur.
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

### Sélecteur de langue

Dans le menu du compte (en haut à droite, à côté du sélecteur de thème),
un `DropdownMenuRadioGroup` « Langue » avec deux choix, **Français** et
**English**, chacun écrit dans sa propre langue. Le choix est enregistré sur
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
(icône `Activity`) pour les administrateurs seulement (`can("manage_users")`),
qui ouvre `/grafana/` — chemin relatif à l'origine, servi par Caddy — dans
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
  mot de passe. Le bouton « Se connecter », et un lien « Je n'ai plus accès
  à mon application » qui n'ouvre rien d'automatique : il explique que seul
  un administrateur peut réinitialiser l'enrôlement, et à qui s'adresser.

Un code refusé s'affiche en `<FormError>` sans vider le champ ; on ne
désactive pas le bouton pour un champ vide (règle d'accessibilité
ci-dessous). Aucune option « se souvenir de cet appareil » : le code est
demandé à chaque connexion d'un compte enrôlé.

### Réouverture d'un dossier

Sur le détail d'un dossier, un bouton **« Rouvrir »** en variante
`outline`, dans les actions de `PageHeader`, rendu **seulement** si
`can("reopen_dossiers")` — c'est-à-dire pour `REOPEN_ROLES`, `admin` et
`super_admin` — et si le dossier est soumis, en contrôle ou non justifié
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

### Menu d'export

Les exports et l'import sont réservés aux administrateurs : le menu
n'apparaît que si `can("export_data")`. C'est un `DropdownMenu` ouvert par
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
`<Loader2 className="animate-spin" />`. L'import (`Upload`) vit sur l'écran
des dossiers, dans le même menu, et propose la prévisualisation
(`dry_run`) avant l'écriture. Pour tous les autres rôles, ni bouton, ni
lien : ils travaillent dans l'application.

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
