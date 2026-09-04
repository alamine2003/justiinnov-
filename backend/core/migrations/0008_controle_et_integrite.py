"""Journal : adresse IP, différences, comptes et connexions ; index ; verrous.

- ``ChangeLog`` gagne l'adresse du client et un ``diff`` sérialisable ; son
  ``object_id`` devient facultatif (un échec de connexion n'a pas d'objet) ;
  index sur les lectures courantes (par date, par pays, par entité).
- ``Country.timezone`` est validé contre la base IANA.
- La configuration du workflow est garantie unique par la base.
"""

import core.models
import core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_workflowconfiguration'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='changelog',
            options={'ordering': ['-created_at', '-pk'], 'verbose_name': 'Historique', 'verbose_name_plural': 'Historiques'},
        ),
        migrations.AddField(
            model_name='changelog',
            name='diff',
            field=models.JSONField(blank=True, default=dict, verbose_name='Différences'),
        ),
        migrations.AddField(
            model_name='changelog',
            name='ip_address',
            field=models.GenericIPAddressField(blank=True, null=True, verbose_name='Adresse IP'),
        ),
        migrations.AlterField(
            model_name='changelog',
            name='action',
            field=models.CharField(choices=[('created', 'Création'), ('updated', 'Mise à jour'), ('reassigned', 'Changement de rattachement'), ('deactivated', 'Désactivation'), ('reactivated', 'Réactivation'), ('deleted', 'Suppression'), ('password_reset', 'Réinitialisation du mot de passe'), ('password_changed', 'Changement de mot de passe'), ('login', 'Connexion'), ('login_failed', 'Échec de connexion'), ('logout', 'Déconnexion')], max_length=20, verbose_name='Action'),
        ),
        migrations.AlterField(
            model_name='changelog',
            name='model_name',
            field=models.CharField(choices=[('country', 'Pays'), ('manager', 'Manager'), ('team', 'Équipe'), ('cost_center', 'Centre de coûts'), ('project', 'Projet'), ('expense_title', 'Intitulé de dépenses'), ('marketing_category', 'Catégorie marketing'), ('budget', 'Enveloppe budgétaire'), ('reallocation', 'Réallocation budgétaire'), ('exchange_rate', 'Taux de change'), ('workflow_configuration', 'Configuration du workflow'), ('user', 'Compte utilisateur')], max_length=32, verbose_name='Entité'),
        ),
        migrations.AlterField(
            model_name='changelog',
            name='object_id',
            field=models.PositiveBigIntegerField(blank=True, null=True, verbose_name="Identifiant d'entité"),
        ),
        migrations.AlterField(
            model_name='country',
            name='timezone',
            field=models.CharField(default='UTC', help_text='Identifiant IANA, ex. Africa/Abidjan.', max_length=64, validators=[core.validators.validate_timezone], verbose_name='Fuseau horaire'),
        ),
        migrations.AlterField(
            model_name='workflowconfiguration',
            name='alert_thresholds',
            field=models.JSONField(default=core.models._seuils_par_defaut, verbose_name="Seuils d'alerte"),
        ),
        migrations.AddIndex(
            model_name='changelog',
            index=models.Index(fields=['created_at'], name='core_changelog_cree_idx'),
        ),
        migrations.AddIndex(
            model_name='changelog',
            index=models.Index(fields=['country', 'created_at'], name='core_changelog_pays_cree_idx'),
        ),
        migrations.AddIndex(
            model_name='changelog',
            index=models.Index(fields=['model_name', 'object_id'], name='core_changelog_entite_idx'),
        ),
        migrations.AddConstraint(
            model_name='workflowconfiguration',
            constraint=models.CheckConstraint(condition=models.Q(('id', 1)), name='core_workflowconfiguration_unique'),
        ),
    ]
