"""Le pays d'une notification ne se supprime plus sous elle.

Une notification atteste que quelqu'un a été prévenu d'un manquement dans
un pays : ``SET_NULL`` aurait effacé ce pays en silence. Comme pour le
journal d'audit, ``PROTECT`` — un pays tracé se désactive, il ne se
supprime pas.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0003_dossier_reopened_kind'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='country',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='notifications', to='core.country', verbose_name='Pays'),
        ),
    ]
