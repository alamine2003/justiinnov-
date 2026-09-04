"""Double authentification obligatoire et langue de l'interface.

``totp_secret`` reste vide tant que le titulaire n'est pas enrôlé ;
``totp_confirmed_at`` est posé au premier code valide. Les comptes existants
partent donc non enrôlés : la plateforme leur est fermée jusqu'à leur
enrôlement, comme pour un mot de passe provisoire.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_roles_manager_dm_df"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="totp_secret",
            field=models.CharField(
                blank=True,
                help_text="Vide tant que le compte n'est pas enrôlé.",
                max_length=64,
                verbose_name="Secret TOTP",
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="totp_confirmed_at",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "Date à laquelle le titulaire a saisi un premier code valide. "
                    "Vide : la plateforme lui reste fermée."
                ),
                null=True,
                verbose_name="Double authentification confirmée le",
            ),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="language",
            field=models.CharField(
                choices=[("fr", "Français"), ("en", "English")],
                default="fr",
                help_text=(
                    "Préférence d'affichage de l'interface. La langue d'une réponse "
                    "de l'API suit l'en-tête Accept-Language de la requête."
                ),
                max_length=8,
                verbose_name="Langue",
            ),
        ),
        migrations.AlterField(
            model_name="userprofile",
            name="teams",
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    "Pour un manager : restreint sa vue à ces équipes. "
                    "Vide, il voit tout son pays."
                ),
                related_name="profiles",
                to="core.team",
                verbose_name="Équipes",
            ),
        ),
        migrations.AlterModelOptions(
            name="userprofile",
            options={
                "ordering": ["user__username"],
                "verbose_name": "Profil",
                "verbose_name_plural": "Profils",
            },
        ),
    ]
