"""Identité d'une ligne importée, tranchée en base.

Deux imports simultanés du même classeur validaient chacun de leur côté
puis écrivaient tous deux : toutes les lignes existaient deux fois. Chaque
ligne importée porte désormais l'empreinte de ce qui la définit — jour,
libellé, montant — et la base refuse la seconde dans le même dossier.

**Stratégie pour l'existant, décidée et non subie.** Les lignes déjà en
base gardent `import_key` à ``NULL`` : après coup, **rien ne distingue une
ligne importée d'une ligne saisie** — l'auteur est le compte qui a lancé
l'import, comme il aurait pu la saisir —, et remplir l'empreinte au
jugé transformerait des dépenses légitimes en doublons refusés. Deux
dépenses identiques saisies à la main sont deux dépenses : c'est
précisément ce que la contrainte partielle protège en ignorant les
``NULL``.

Conséquences, à connaître :

- **La migration ne peut pas échouer sur des données existantes** : toutes
  les lignes reçoivent ``NULL``, et une contrainte ``UNIQUE`` partielle
  ``WHERE import_key IS NOT NULL`` ne regarde aucune d'elles. Elle
  s'applique aux imports **à venir**.
- **Les doublons déjà présents ne sont pas corrigés par cette migration.**
  Ils se listent avec ``manage.py doublons_importes`` (brouillons d'un même
  dossier, même jour, même libellé, même montant) et se retirent, s'il y a
  lieu, **par leur auteur depuis l'application** — un brouillon se supprime,
  une ligne déclarée non : elle se rouvre puis se corrige, sous les yeux de
  l'audit. Aucune suppression automatique : la plateforme ne purge rien.
- **Un réimport d'un classeur dont les lignes existent déjà** reste refusé
  ligne par ligne, même sans empreinte : la validation compare le jour, le
  libellé et le montant aux lignes en base (``_lignes_en_base``). La
  contrainte ne remplace pas cette vérification, elle tranche ce que
  celle-ci ne peut pas voir — l'autre import en cours au même instant.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("expenses", "0013_fichier_a_supprimer"),
    ]

    operations = [
        migrations.AddField(
            model_name="expense",
            name="import_key",
            field=models.CharField(
                blank=True, editable=False, max_length=64, null=True,
                verbose_name="Empreinte d'import",
            ),
        ),
        migrations.AddConstraint(
            model_name="expense",
            constraint=models.UniqueConstraint(
                condition=models.Q(("import_key__isnull", False)),
                fields=("dossier", "import_key"),
                name="ligne_importee_unique_par_dossier",
            ),
        ),
    ]
