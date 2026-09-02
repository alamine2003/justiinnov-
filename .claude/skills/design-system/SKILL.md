---
name: design-system
description: Charge les règles d'interface du projet avant d'écrire ou de modifier un écran React — page, formulaire, tableau, dialogue — et avant tout choix de couleur, d'espacement ou de composant. Les règles elles-mêmes vivent dans DESIGN.md à la racine.
---

# Design system

Les règles ne sont pas ici : elles sont dans **`DESIGN.md`**, à la racine du
dépôt. Ce fichier est volontairement un simple pointeur — deux copies des mêmes
règles finiraient par diverger, et c'est le genre de dérive que ce projet a
déjà payé ailleurs.

## À faire

1. **Lisez `DESIGN.md`** en entier avant de toucher à un écran.
2. Appliquez-le tel quel : n'inventez pas de couleur, ne refaites pas un
   composant qui existe, ne recalculez pas un chiffre côté interface.
3. En cas de conflit entre `DESIGN.md` et un composant existant, dites-le
   plutôt que de trancher en silence.
4. Terminez par la boucle de vérification décrite en fin de `DESIGN.md` :
   `tsc`, lint, tests, puis **les captures d'écran**. Un écran n'est pas fini
   tant qu'il n'a pas été regardé.

## Si vous faites évoluer le système

Toute nouvelle règle — une teinte, un espacement, un composant partagé — se
consigne dans `DESIGN.md`, pas ici et pas dans le composant qui l'a inspirée.
