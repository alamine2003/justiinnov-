"""Journalise l'activation et la réinitialisation de la double authentification."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_journal_pays_protege"),
    ]

    operations = [
        migrations.AlterField(
            model_name="changelog",
            name="action",
            field=models.CharField(
                choices=[
                    ("created", "Création"),
                    ("updated", "Mise à jour"),
                    ("reassigned", "Changement de rattachement"),
                    ("deactivated", "Désactivation"),
                    ("reactivated", "Réactivation"),
                    ("deleted", "Suppression"),
                    ("password_reset", "Réinitialisation du mot de passe"),
                    ("password_changed", "Changement de mot de passe"),
                    ("login", "Connexion"),
                    ("login_failed", "Échec de connexion"),
                    ("logout", "Déconnexion"),
                    ("totp_confirmed", "Double authentification activée"),
                    ("totp_reset", "Double authentification réinitialisée"),
                ],
                max_length=20,
                verbose_name="Action",
            ),
        ),
    ]
