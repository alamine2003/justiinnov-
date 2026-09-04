"""Aligne les rôles sur l'organisation réelle.

Côté pays : manager, DM (son supérieur), DF (supérieur du DM). Côté siège :
la RH est administratrice, la direction (DG, DO, CEO) et les développeurs
sont super administrateurs. Les anciens rôles « direction des opérations »
et « auditeur » n'existent plus : la DO attribue les enveloppes en tant que
super administratrice, l'audit revient à la RH.
"""

from django.db import migrations, models

CORRESPONDANCE = {
    "owner": "manager",
    "country_manager": "dm",
    "controller": "df",
    "doo": "super_admin",
    "auditor": "admin",
}


def renommer_les_roles(apps, schema_editor):
    UserProfile = apps.get_model("accounts", "UserProfile")
    for ancien, nouveau in CORRESPONDANCE.items():
        UserProfile.objects.filter(role=ancien).update(role=nouveau)


def retablir_les_roles(apps, schema_editor):
    UserProfile = apps.get_model("accounts", "UserProfile")
    # Les fusions (doo → super_admin, auditor → admin) ne se défont pas :
    # on ne sait plus qui était quoi. Seuls les renommages simples reviennent.
    for ancien, nouveau in (("manager", "owner"), ("dm", "country_manager"), ("df", "controller")):
        UserProfile.objects.filter(role=ancien).update(role=nouveau)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(renommer_les_roles, retablir_les_roles),
        migrations.AlterField(
            model_name="userprofile",
            name="role",
            field=models.CharField(
                choices=[
                    ("super_admin", "Super administrateur (DG, DO, CEO, DEV)"),
                    ("admin", "Administrateur (RH)"),
                    ("df", "DF — direction financière"),
                    ("dm", "DM — supérieur du manager"),
                    ("manager", "Manager"),
                ],
                max_length=32,
                verbose_name="Rôle",
            ),
        ),
    ]
