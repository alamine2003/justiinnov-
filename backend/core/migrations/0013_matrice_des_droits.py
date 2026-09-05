"""Matrice des droits configurable (décision 43)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0012_actions_double_authentification")]

    operations = [
        migrations.AddField(
            model_name="workflowconfiguration",
            name="capability_roles",
            field=models.JSONField(blank=True, default=dict, verbose_name="Matrice des droits"),
        ),
    ]
