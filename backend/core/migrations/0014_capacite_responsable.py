"""Le responsable a ses propres capacités, séparées de celles du pays.

``managers.create`` et ``managers.update`` remplacent ``countries.create`` et
``countries.update`` pour l'inscription d'un responsable et son rattachement
à un pays. Les deux nouvelles clés ne sont pas verrouillées : elles
s'ouvrent au pays depuis « Configuration › Permissions », ce que les
capacités du pays refusent — un pays ne change pas sa propre devise.

**Une matrice déjà réglée doit garder son réglage.** Une clé absente de
``capability_roles`` prend son défaut (``_ADMINISTRATEURS``) : sans cette
migration, une installation où un administrateur aurait ouvert
``countries.update`` à un autre rôle le verrait perdre, en silence, le côté
« responsable » de ce qu'il avait accordé. On recopie donc le réglage du
pays dans celui du responsable, et seulement s'il existe.

La réciproque n'existe pas : revenir en arrière ne peut que retirer les deux
clés nouvelles, le réglage d'origine du pays étant resté en place.
"""

from django.db import migrations

_REPRISES = (
    ("countries.create", "managers.create"),
    ("countries.update", "managers.update"),
)


def reprendre_le_reglage_du_pays(apps, schema_editor):
    WorkflowConfiguration = apps.get_model("core", "WorkflowConfiguration")
    for configuration in WorkflowConfiguration.objects.all():
        choix = configuration.capability_roles
        if not isinstance(choix, dict):
            continue
        modifie = False
        for depuis, vers in _REPRISES:
            if depuis in choix and vers not in choix:
                choix[vers] = choix[depuis]
                modifie = True
        if modifie:
            configuration.capability_roles = choix
            configuration.save(update_fields=["capability_roles"])


def oublier_le_reglage_du_responsable(apps, schema_editor):
    WorkflowConfiguration = apps.get_model("core", "WorkflowConfiguration")
    for configuration in WorkflowConfiguration.objects.all():
        choix = configuration.capability_roles
        if not isinstance(choix, dict):
            continue
        retenus = {cle: valeur for cle, valeur in choix.items()
                   if cle not in {vers for _, vers in _REPRISES}}
        if retenus != choix:
            configuration.capability_roles = retenus
            configuration.save(update_fields=["capability_roles"])


class Migration(migrations.Migration):
    dependencies = [("core", "0013_matrice_des_droits")]

    operations = [
        migrations.RunPython(
            reprendre_le_reglage_du_pays, oublier_le_reglage_du_responsable
        ),
    ]
