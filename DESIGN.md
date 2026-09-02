# DESIGN.md — système d'interface

> Référence unique de l'interface. **À lire avant toute modification d'écran.**
> Les tokens vivent dans `frontend/src/index.css` ; ce document dit comment
> s'en servir.

L'application sert des contrôleurs et des responsables pays qui lisent des
chiffres et cherchent des preuves. Trois principes en découlent :

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
| Justifié, actif, validé, approuvé | `bg-emerald-500` |
| En contrôle, alerte, incomplet, en attente | `bg-amber-500` |
| Soumis, information | `bg-blue-500` |
| Brouillon | `bg-slate-500` |
| Archivé, clôturé | `bg-zinc-500`, `bg-zinc-600` |
| Non justifié, rejeté, dépassement | `bg-destructive` |

Les correspondances sont centralisées dans
`components/expenses/status-badge.tsx` et dans les tables `*_LABELS` de
`lib/types.ts`. Un nouveau statut s'ajoute **là**, jamais dans la page qui
l'affiche.

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
| Erreur de formulaire | encadré `bg-destructive/10` avec `role="alert"` |
| Avertissement métier | `<Alert>` neutre |

Un état vide doit dire **quoi faire**, pas seulement constater le vide.
« Aucun dossier — Créez un dossier pour y rattacher vos dépenses » vaut mieux
que « Aucune donnée ».

---

## Droits et données

- Les droits viennent de `/api/me/` via `can("record_expenses")`,
  `can("validate_expenses")`, `can("view_audit")`… **Ne recopiez jamais une
  table de rôles dans un composant** : elle divergerait du serveur. Masquer une
  action est un confort ; le refus reste côté serveur.
- Les montants transitent en **chaîne** pour préserver la précision décimale.
  La conversion en `number` n'a lieu qu'au formatage.
- Formatage : `formatAmount`, `formatRate`, `formatDate`, `formatDateIn`.
- Les heures d'une dépense se lisent dans le **fuseau du pays**
  (`formatDateIn(date, country_timezone)`), pas dans celui du lecteur.

---

## Accessibilité

- Tout bouton à icône seule porte un `aria-label`.
- Un message d'erreur porte `role="alert"`.
- **Ne désactivez pas un bouton de soumission pour cause de champ vide** : il
  n'explique rien. Validez à la soumission et affichez la raison.
- Conservez l'anneau de focus sur tout élément interactif construit à la main.
- Libellés liés par `htmlFor` / `id`.

---

## Vérifier avant de conclure

```bash
cd frontend
npx tsc -b && npm run lint && npm run test

SHOT_HQ_USER=… SHOT_HQ_PASSWORD=… \
SHOT_COUNTRY_USER=… SHOT_COUNTRY_PASSWORD=… \
npx tsx scripts/screenshot.ts     # parcours complet, siège et pays
npx tsx scripts/shot-login.ts     # connexion, grand écran et mobile
```

Les deux scripts **échouent si la console du navigateur a produit la moindre
erreur**. Regardez les captures : plusieurs défauts de ce projet — un
`method-wrapper` affiché en clair, une page qui plantait, un bouton d'édition
jamais rendu — n'ont été trouvés que là.

---

## Points connus

- Le thème sombre est **entièrement défini** dans les tokens, mais aucun
  sélecteur ne pose la classe `.dark` : il est inatteignable. Ajouter un
  basculement suffirait, tout le système suivrait.
- Les couleurs de statut sont des couleurs Tailwind brutes, hors tokens :
  elles ne varient pas avec le thème. Assumé tant que le thème sombre dort.
