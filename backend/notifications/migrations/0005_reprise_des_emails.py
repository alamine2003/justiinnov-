"""Titre élargi et reprise des e-mails.

Le titre passe de 200 à 500 caractères : un libellé de dépense (250) ou le
nom complet d'une enveloppe, préfixe compris, dépassait la colonne, et
l'erreur — avalée — annulait la transition en cours. Les deux champs
d'envoi permettent de reprendre un e-mail qui n'est pas parti, après
redémarrage compris.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0004_pays_protege"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="title",
            field=models.CharField(max_length=500, verbose_name="Titre"),
        ),
        migrations.AddField(
            model_name="notification",
            name="email_attempted_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="Dernier essai d'envoi le"
            ),
        ),
        migrations.AddField(
            model_name="notification",
            name="email_attempts",
            field=models.PositiveSmallIntegerField(
                default=0, verbose_name="Essais d'envoi"
            ),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(
                condition=models.Q(("emailed_at__isnull", True)),
                fields=["email_attempted_at"],
                name="notification_email_a_faire_idx",
            ),
        ),
    ]
