"""Trois rôles : le DM et le DF disparaissent (décision 89).

Le contrôle qu'ils se partageaient revient à l'administrateur seul. Un
compte qui portait l'un de ces rôles ne peut pas garder une valeur que
l'application ne connaît plus ; il ne reçoit pas non plus d'office les
droits d'un administrateur — comptes, configuration, enveloppes —, qui
sont bien plus larges que ce qu'il faisait. Il passe donc **désactivé**,
au rôle le moins étendu (``manager``), et un administrateur décide de son
sort : lui donner le rôle d'administrateur s'il contrôle désormais, puis
le réactiver. Rien n'est supprimé. Chaque compte repris laisse une entrée
dans l'historique (``ChangeLog``), avec son ancien rôle.

La migration inverse ne sait pas qui était DM ou DF que par l'historique :
elle ne réécrit rien.
"""

from django.db import migrations, models

ANCIENS_ROLES = ("dm", "df")
AUTEUR = "migration accounts.0006_trois_roles"


def reprendre_les_comptes(apps, schema_editor):
    UserProfile = apps.get_model("accounts", "UserProfile")
    ChangeLog = apps.get_model("core", "ChangeLog")
    for profil in (
        UserProfile.objects.filter(role__in=ANCIENS_ROLES)
        .select_related("user")
        .order_by("pk")
    ):
        user = profil.user
        ancien = profil.role
        etait_actif = user.is_active
        profil.role = "manager"
        profil.save(update_fields=["role"])
        user.is_active = False
        user.is_staff = False
        user.is_superuser = False
        user.save(update_fields=["is_active", "is_staff", "is_superuser"])
        # Une entrée par compte : la seule mémoire, après cette migration,
        # de qui était DM ou DF.
        entree = ChangeLog(
            model_name="user",
            object_id=user.pk,
            label=user.username,
            action="deactivated",
            from_value=ancien,
            to_value="manager",
            changed_fields=["role", "is_active"],
            diff={"role": [ancien, "manager"], "is_active": [etait_actif, False]},
            performed_by=AUTEUR,
        )
        entree.save()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_totp_dernier_compteur"),
        ("core", "0014_capacite_responsable"),
    ]

    operations = [
        migrations.RunPython(reprendre_les_comptes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="userprofile",
            name="role",
            field=models.CharField(
                choices=[
                    ("super_admin", "Super administrateur (DG, DO, CEO, DEV)"),
                    ("admin", "Administrateur (RH)"),
                    ("manager", "Manager (pays)"),
                ],
                max_length=32,
                verbose_name="Rôle",
            ),
        ),
        migrations.AlterField(
            model_name="userprofile",
            name="countries",
            field=models.ManyToManyField(
                blank=True,
                help_text="Le pays du manager. Le siège voit tous les pays.",
                related_name="profiles",
                to="core.country",
                verbose_name="Pays du périmètre",
            ),
        ),
    ]
