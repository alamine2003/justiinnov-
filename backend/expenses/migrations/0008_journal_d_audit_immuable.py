"""Rend le journal d'audit immuable au niveau de la base.

L'application ne modifie ni ne supprime jamais une entrée d'audit, et
l'admin Django l'interdit désormais. Mais un bug, une commande ou un accès
direct à la base pouvaient encore altérer l'historique. Un déclencheur
PostgreSQL rejette tout UPDATE ou DELETE : la trace survit à tout ce qui
n'est pas une suppression de la table elle-même. Idée reprise du premier
schéma SQL du projet (0004_audit_immutability.sql).
"""

from django.db import migrations

FONCTION = """
CREATE OR REPLACE FUNCTION refuser_modification_journal()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'Le journal % est en ajout seul : % interdit (id=%)',
    TG_TABLE_NAME, TG_OP, OLD.id;
END;
$$ LANGUAGE plpgsql;
"""

DECLENCHEUR = """
CREATE TRIGGER journal_audit_immuable
  BEFORE UPDATE OR DELETE ON expenses_auditlog
  FOR EACH ROW EXECUTE FUNCTION refuser_modification_journal();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("expenses", "0007_controle_et_integrite"),
    ]

    operations = [
        migrations.RunSQL(
            FONCTION,
            reverse_sql="DROP FUNCTION IF EXISTS refuser_modification_journal() CASCADE;",
        ),
        migrations.RunSQL(
            DECLENCHEUR,
            reverse_sql="DROP TRIGGER IF EXISTS journal_audit_immuable ON expenses_auditlog;",
        ),
    ]
