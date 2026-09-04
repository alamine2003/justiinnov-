"""Le DM et le DF rejoignent le siège ; l'obligation de 2FA devient une politique.

Aucune donnée ne change : les valeurs des rôles sont les mêmes. Seuls les
libellés bougent — le DM n'est plus « supérieur du manager » dans le pays
mais « directeur manager » au siège, où il met les dossiers en contrôle
avant que le DF ne tranche — et l'aide du champ ``totp_confirmed_at``, qui
ne peut plus promettre une plateforme fermée : elle ne l'est que si
``settings.TOTP_REQUIRED`` l'exige.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_totp_langue_equipes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="userprofile",
            name="role",
            field=models.CharField(
                choices=[
                    ("super_admin", "Super administrateur (DG, DO, CEO, DEV)"),
                    ("admin", "Administrateur (RH)"),
                    ("df", "DF — directeur financier (siège)"),
                    ("dm", "DM — directeur manager (siège)"),
                    ("manager", "Manager (pays)"),
                ],
                max_length=32,
                verbose_name="Rôle",
            ),
        ),
        migrations.AlterField(
            model_name="userprofile",
            name="totp_confirmed_at",
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "Date à laquelle le titulaire a saisi un premier code valide. "
                    "Vide : le compte n'est pas enrôlé, et la plateforme lui est "
                    "fermée si la politique l'exige."
                ),
                null=True,
                verbose_name="Double authentification confirmée le",
            ),
        ),
    ]
