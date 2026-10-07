"""Les codes des trois types de projets d'origine (décisions 100 et 119).

La liste des types vit en base (``ProjectType``) et le super administrateur
la complète ; ces trois codes, eux, existent partout depuis la 2.0 — la
migration ``core.0018`` les crée — et servent aux jeux de démonstration et
aux tests, qui ouvrent des projets sans passer par la configuration.
"""

CONGRES = "congres"
VOYAGE = "voyage"
SOUTIEN_FINANCIER = "soutien_financier"

#: Les types d'origine, dans l'ordre et sous les noms de la migration
#: ``core.0018`` : code, nom, nom anglais.
TYPES_D_ORIGINE = (
    (CONGRES, "Congrès", "Congress"),
    (VOYAGE, "Voyage", "Trip"),
    (SOUTIEN_FINANCIER, "Soutien financier", "Financial support"),
)


def assurer_les_types_d_origine():
    """Recrée les types d'origine s'ils manquent, et les rend.

    Pour les cas de test qui vident la base (``TransactionTestCase``) et
    perdent ainsi ce que les migrations y avaient mis.
    """
    from .models import ProjectType

    return [
        ProjectType.objects.get_or_create(
            code=code, defaults={"name": nom, "name_en": nom_en, "ordre": ordre}
        )[0]
        for ordre, (code, nom, nom_en) in enumerate(TYPES_D_ORIGINE, start=1)
    ]
