# Index sur la clé d'unicité : ``notify`` la consulte pour chaque alerte.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["dedup_key"], name="notification_dedup_key_idx"),
        ),
    ]
