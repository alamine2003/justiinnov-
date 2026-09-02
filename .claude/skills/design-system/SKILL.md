---
name: design-system
description: Règles d'interface de la plateforme de contrôle budgétaire — palette, typographie, composants partagés, états de tableau, accessibilité et boucle de vérification visuelle. À charger avant d'écrire ou de modifier un écran React de ce projet (page, formulaire, tableau, dialogue), et avant tout choix de couleur ou d'espacement.
---

# Design system — contrôle budgétaire

Interface en français, sobre, dense en information. Elle sert des contrôleurs
et des responsables pays qui lisent des chiffres et cherchent des preuves : la
lisibilité prime sur l'effet.

## Couleurs — ne jamais en inventer

La palette est **monochrome** et vit dans les tokens de `src/index.css`
(`oklch`, avec un thème clair et un thème sombre). N'écrivez jamais une couleur
en dur pour un fond, un texte ou une bordure : utilisez les classes de token.

| Usage | Classe |
|---|---|
| Fond de page | `bg-background` |
| Surface (carte, dialogue) | `bg-card` |
| Texte principal | `text-foreground` |
| Texte secondaire | `text-muted-foreground` |
| Bordures | `border-border` (souvent `border-border/60`) |
| Action principale | `bg-primary text-primary-foreground` |
| Survol discret | `hover:bg-accent` |
| Erreur, danger | `text-destructive`, `bg-destructive/10` |

**Seule exception, et elle est close** : les couleurs sémantiques de statut,
déjà en place. Reprenez exactement ces teintes, n'en ajoutez pas :

| Sens | Teinte |
|---|---|
| Justifié, actif, validé | `bg-emerald-500` |
| En contrôle, alerte, incomplet | `bg-amber-500` |
| Soumis, information | `bg-blue-500` |
| Brouillon, archivé, clôturé | `bg-slate-500`, `bg-zinc-500/600` |
| Non justifié, rejet, dépassement | `bg-destructive` |

Les correspondances sont centralisées dans
`components/expenses/status-badge.tsx`. Un nouveau statut s'y ajoute, pas dans
la page qui l'affiche.

## Composants partagés — les utiliser, pas les refaire

| Besoin | Composant |
|---|---|
| Titre de page + description + actions | `ui/page-header` → `<PageHeader>` |
| Tableau vide | `ui/table-states` → `<EmptyRow>` |
| Tableau en chargement | `ui/table-states` → `<SkeletonRows>` |
| Pagination | `ui/pagination` → `<Pagination>`, `PAGE_SIZE` |
| Liste déroulante | `ui/native-select` → `<NativeSelect>` |
| Statut de dépense ou de pièce | `expenses/status-badge` |
| Actions de workflow | `expenses/workflow-actions` |

Le projet utilise **base-ui** sous shadcn, dont l'API diffère de Radix. Pour
les listes déroulantes, préférez `NativeSelect` : comportement clavier natif,
rendu correct sur mobile, aucun risque d'API.

## Structure d'un écran

```tsx
<div className="space-y-6">
  <PageHeader title="…" description="…">{/* actions */}</PageHeader>
  {error && <Alert variant="destructive">…</Alert>}
  {/* filtres */}
  <Card className="border-border/60 shadow-sm">
    <CardContent className="pt-6">
      <div className="overflow-hidden rounded-lg border border-border/60">
        <Table>…</Table>
      </div>
      <Pagination … />
    </CardContent>
  </Card>
</div>
```

- Espacement vertical d'une page : `space-y-6`. Dans une carte : `space-y-3`.
- Titre de page : `text-2xl font-semibold tracking-tight` (fourni par
  `PageHeader`). Titre de section : `text-sm font-semibold`.
- Montants alignés à droite ; un écart non nul se met en `text-destructive`.
- Un tableau large se met dans `overflow-x-auto`, jamais la page entière.

## Règles de fond

- **Les chiffres viennent du serveur.** Ne recalculez jamais un solde, un
  écart ou un taux dans l'interface : affichez ce que l'API renvoie, formaté
  par `formatAmount`, `formatRate`, `formatDateIn`.
- **Les montants transitent en chaîne** pour préserver la précision décimale.
  La conversion en `number` n'a lieu qu'au formatage.
- **Les heures se lisent dans le fuseau du pays** (`formatDateIn(date,
  country_timezone)`), pas dans celui du lecteur.
- **Les droits viennent de `/api/me/`** via `can("…")`. Ne recopiez jamais une
  table de rôles dans un composant : elle divergerait du serveur. Masquer une
  action est un confort, le refus reste côté serveur.

## Accessibilité

- Tout bouton porteur d'une seule icône a un `aria-label`.
- Un message d'erreur porte `role="alert"`.
- Ne désactivez pas un bouton de soumission pour cause de champ vide : il
  n'explique rien. Validez à la soumission et affichez la raison.
- Conservez l'anneau de focus (`focus-visible:ring-*`) sur tout élément
  interactif construit à la main.
- Les libellés sont liés par `htmlFor` / `id`.

## Vérifier avant de conclure

Un écran n'est pas fini tant qu'il n'a pas été **regardé**.

```bash
cd frontend
SHOT_HQ_USER=… SHOT_HQ_PASSWORD=… \
SHOT_COUNTRY_USER=… SHOT_COUNTRY_PASSWORD=… \
npx tsx scripts/screenshot.ts       # parcours complet, deux profils
npx tsx scripts/shot-login.ts       # connexion, grand écran et mobile
```

Les deux scripts échouent si la console du navigateur a produit la moindre
erreur. Vérifiez ensuite `npx tsc -b`, `npm run lint` et `npm run test`.

## Points connus

- Le thème sombre est défini dans les tokens mais **aucun sélecteur ne
  l'active** : la classe `.dark` n'est posée nulle part. Si vous ajoutez un
  basculement, tout le système de tokens suivra déjà.
- Les couleurs de statut sont des couleurs Tailwind brutes, hors tokens :
  elles ne changent pas avec le thème. C'est assumé tant que le thème sombre
  n'est pas activé.
