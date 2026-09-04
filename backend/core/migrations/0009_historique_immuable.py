"""Rend l'historique des modifications immuable au niveau de la base.

Même principe que pour le journal d'audit des dépenses : la fonction
``refuser_modification_journal`` est créée par ``expenses.0008`` ; ici on ne
fait qu'y attacher la table ``core_changelog``.
"""

from django.db import migrations

DECLENCHEUR = """
CREATE TRIGGER historique_immuable
  BEFORE UPDATE OR DELETE ON core_changelog
  FOR EACH ROW EXECUTE FUNCTION refuser_modification_journal();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0008_controle_et_integrite"),
        ("expenses", "0008_journal_d_audit_immuable"),
    ]

    operations = [
        migrations.RunSQL(
            DECLENCHEUR,
            reverse_sql="DROP TRIGGER IF EXISTS historique_immuable ON core_changelog;",
        ),
    ]
