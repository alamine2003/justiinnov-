"""La matrice réglée avant la décision 89 suit les trois rôles.

``WorkflowConfiguration.capability_roles`` ne garde que ce qui s'écarte du
défaut. Réglée sous l'ancien régime, elle peut encore porter :

- les rôles ``dm`` et ``df``, que l'application ne connaît plus ;
- un choix sur ``data.import``, passé des administrateurs au pays : un
  réglage « administrateurs » y deviendrait, une fois les verrous
  appliqués, un import que plus personne ne peut faire ;
- un choix sur ``rectifications.request``, dont l'administrateur sort par
  défaut — il ne trancherait pas sa propre demande.

Les deux rôles sont retirés de chaque ligne, et ces deux capacités
reviennent à leur nouveau défaut ; un administrateur les règle à nouveau
s'il le souhaite. Chaque configuration modifiée laisse une entrée dans
l'historique (``ChangeLog``) avec l'avant et l'après. Rien d'autre ne
bouge : les verrous rendent déjà sans effet ce qu'une ligne de
déclaration ou de contrôle porterait de trop.

La migration inverse ne réécrit rien : l'historique garde l'ancien réglage.
"""

import json

from django.db import migrations

ANCIENS_ROLES = {"dm", "df"}
REVENUES_AU_DEFAUT = ("data.import", "rectifications.request")
AUTEUR = "migration accounts.0007_matrice_trois_roles"


def suivre_les_trois_roles(apps, schema_editor):
    WorkflowConfiguration = apps.get_model("core", "WorkflowConfiguration")
    ChangeLog = apps.get_model("core", "ChangeLog")
    for configuration in WorkflowConfiguration.objects.order_by("pk"):
        choix = configuration.capability_roles
        if not isinstance(choix, dict):
            continue
        retenus = {}
        for cle, roles in choix.items():
            if cle in REVENUES_AU_DEFAUT:
                continue
            if isinstance(roles, list):
                roles = [role for role in roles if role not in ANCIENS_ROLES]
            retenus[cle] = roles
        if retenus == choix:
            continue
        changes = sorted(set(choix) | set(retenus))
        changes = [cle for cle in changes if choix.get(cle) != retenus.get(cle)]
        configuration.capability_roles = retenus
        configuration.save(update_fields=["capability_roles"])
        ChangeLog(
            model_name="workflow_configuration",
            object_id=configuration.pk,
            label="Matrice des droits",
            action="updated",
            from_value=json.dumps({c: choix.get(c) for c in changes}, ensure_ascii=False),
            to_value=json.dumps({c: retenus.get(c) for c in changes}, ensure_ascii=False),
            changed_fields=changes,
            diff={c: [choix.get(c), retenus.get(c)] for c in changes},
            performed_by=AUTEUR,
        ).save()


class Migration(migrations.Migration):
    dependencies = [("accounts", "0006_trois_roles")]

    operations = [
        migrations.RunPython(suivre_les_trois_roles, migrations.RunPython.noop),
    ]
