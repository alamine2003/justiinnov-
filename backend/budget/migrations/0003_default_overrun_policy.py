import budget.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("budget", "0002_remove_budget_unique_enveloppe_pays_annee_and_more")]

    operations = [
        migrations.AlterField(
            model_name="budget",
            name="overrun_policy",
            field=models.CharField(
                choices=[
                    ("block", "Bloquer"),
                    ("warn", "Alerter"),
                    ("approval", "Soumettre à approbation"),
                ],
                default=budget.models.default_overrun_policy,
                max_length=20,
                verbose_name="Politique de dépassement",
            ),
        )
    ]
