"""L'API des projets, la rubrique principale depuis la 2.0 (décision 100).

Elle vivait dans ``accounts/referentiel.py`` et importait ``expenses`` dans
quatre fonctions : un projet naît avec ses dossiers (décision 106) et lit
l'historique du circuit (décision 110). ``accounts`` précède ``expenses``
dans l'ordre des applications ; la vue vient donc ici, au rang où ce dont
elle dépend existe déjà (décision 125). Route et nom inchangés :
``/api/projects/``, ``basename="project"``.
"""

from django.db import transaction
from django.db.models import Count, Q
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.perimetre import compter_par_pays
from accounts.permissions import get_access
# Le sérialiseur cloisonné du référentiel : le pays d'un projet ne peut
# être que l'un de ceux du compte (``ChampCloisonne``).
from accounts.referentiel import ProjectSerializer, ScopedViewSet
from core.journal import Trace
from core.models import Project
from core.numerotation import creer_projet
from core.requetes import motif_du_journal
from core.serializers import (
    HistoriqueDeProjetSerializer,
    ParPaysSerializer,
    RenommerProjetSerializer,
)

from .historique import historique_du_projet
from .predefinis import EQUIPE_DU_PROJET, creer_les_dossiers_predefinis


class ProjectViewSet(ScopedViewSet):
    """Les projets : la rubrique principale depuis la 2.0 (décision 100).

    Le pays les crée (``projets.create``, déclaration : jamais le siège) et
    chacun naît avec ses dossiers prédéfinis (décision 106) ; le pays en
    corrige le titre (``projets.rename``) ; le siège en change le statut,
    la description, les désactive et type ceux d'avant la 2.0
    (``projets.update``). Toute modification exige un motif, gardé au
    journal (décision 109). La référence est attribuée à la création, ligne
    du pays verrouillée (``core.numerotation``).
    """

    # Le type est lu par chaque ligne (``kind_display``) : sans lui, une
    # requête par projet typé.
    queryset = Project.objects.select_related("country", "kind").all().order_by("-created_at")
    serializer_class = ProjectSerializer
    filterset_fields = ["country", "status", "is_active", "kind", "is_historical"]
    search_fields = ["name", "reference"]
    ordering_fields = ["created_at", "name", "reference"]
    write_capability = "projets.update"
    action_write_capabilities = {
        "create": "projets.create", "rename": "projets.rename", "completer": "projets.update",
    }
    # L'historique d'un projet lit le journal d'audit de ses dossiers : il
    # en suit la capacité, jamais ouverte au pays (``audit.read``), pas
    # celle de l'historique du référentiel, que la matrice peut lui ouvrir.
    action_read_capabilities = {"historique": "audit.read"}

    def get_queryset(self):
        # Le nombre de dossiers est celui que le lecteur verra en ouvrant le
        # projet : cloisonné comme la liste des dossiers — un manager
        # rattaché à des équipes ne compte que les leurs.
        access = get_access(self.request.user)
        visibles = Q()
        if access is not None and access.team_ids is not None:
            visibles &= Q(dossiers__team_id__in=access.team_ids)
        return super().get_queryset().annotate(
            dossier_count=Count("dossiers", filter=visibles, distinct=True)
        )

    def get_serializer_class(self):
        if self.action == "rename":
            return RenommerProjetSerializer
        return super().get_serializer_class()

    def _equipe_des_dossiers(self, equipe):
        """L'équipe des dossiers prédéfinis, revalidée contre le périmètre.

        Un manager rattaché à des équipes en choisit une des siennes : ses
        dossiers, et leurs lignes, lui resteraient sinon invisibles
        (cloisonnement par équipe).
        """
        access = get_access(self.request.user)
        if access is None or access.team_ids is None:
            return equipe
        if equipe is None:
            raise serializers.ValidationError({"team": _("Choisissez une de vos équipes.")})
        if equipe.pk not in access.team_ids:
            raise serializers.ValidationError({"team": _("Choisissez une de vos équipes.")})
        return equipe

    def perform_create(self, serializer):
        self._check_country_scope(serializer)
        serializer.prendre_le_motif()
        donnees = dict(serializer.validated_data)
        equipe = self._equipe_des_dossiers(donnees.pop("team", None))
        with transaction.atomic():
            projet = creer_projet(Project(**donnees))
            crees = creer_les_dossiers_predefinis(
                projet, auteur=self.request.user.username, equipe=equipe,
                trace=Trace.depuis_requete(self.request),
            )
            # Un projet sans dossier ne servirait à rien, et le pays n'a
            # aucun moyen d'en ouvrir : il ne se crée pas.
            if not crees:
                raise serializers.ValidationError({"kind": _(
                    "Ce projet ne recevrait aucun dossier : il doit être actif, et son "
                    "type de projet doit avoir des types de dossiers actifs."
                )})
        # Relu par le queryset de la vue : la réponse compte ses dossiers.
        serializer.instance = self.get_queryset().get(pk=projet.pk)

    def perform_update(self, serializer):
        motif = serializer.prendre_le_motif()
        a_typer = not serializer.instance.kind_id and not serializer.instance.is_historical
        with transaction.atomic(), motif_du_journal(motif):
            projet = serializer.save()
            # Un projet d'avant la 2.0 que le siège vient de typer reçoit
            # ses dossiers prédéfinis ; ils reviennent au pays (sans auteur).
            if a_typer and projet.kind_id:
                creer_les_dossiers_predefinis(
                    projet, equipe=EQUIPE_DU_PROJET,
                    trace=Trace.depuis_requete(self.request),
                )

    @extend_schema(request=RenommerProjetSerializer, responses=ProjectSerializer)
    @action(detail=True, methods=["post"])
    def rename(self, request, pk=None):
        """Change le titre du projet, motif à l'appui (décisions 108 et 109)."""
        projet = self.get_object()
        entree = RenommerProjetSerializer(data=request.data)
        entree.is_valid(raise_exception=True)
        nom = entree.validated_data["name"]
        with transaction.atomic():
            projet = Project.objects.select_for_update().get(pk=projet.pk)
            if nom != projet.name:
                if Project.objects.filter(country=projet.country, name=nom).exclude(pk=projet.pk).exists():
                    raise serializers.ValidationError(
                        {"name": _("Ce projet existe déjà pour ce pays.")}
                    )
                projet.name = nom
                with motif_du_journal(entree.validated_data["motif"]):
                    projet.save(update_fields=["name", "updated_at"])
        lu = self.get_queryset().get(pk=projet.pk)
        return Response(ProjectSerializer(lu, context=self.get_serializer_context()).data)

    @extend_schema(request=None, responses=ProjectSerializer)
    @action(detail=True, methods=["post"])
    def completer(self, request, pk=None):
        """Ouvre les dossiers prédéfinis qui manquent au projet (décision 106).

        Un projet réactivé, un type de dossier ajouté depuis, un projet typé
        avant la décision : le siège le complète à la demande, jamais
        d'office. Les dossiers ouverts ainsi n'ont pas d'auteur : ils
        reviennent au pays. Ils prennent l'équipe que portent tous les
        dossiers prédéfinis du projet, s'il n'y en a qu'une : sans elle, le
        manager de cette équipe ne verrait pas le dossier ajouté.
        """
        projet = self.get_object()
        if not projet.accepte_des_dossiers:
            raise serializers.ValidationError({"project": _(
                "Ce projet n'accepte pas de dossier : il doit être actif et typé."
            )})
        creer_les_dossiers_predefinis(
            projet, equipe=EQUIPE_DU_PROJET, trace=Trace.depuis_requete(request)
        )
        lu = self.get_queryset().get(pk=projet.pk)
        return Response(ProjectSerializer(lu, context=self.get_serializer_context()).data)

    @extend_schema(responses=HistoriqueDeProjetSerializer)
    @action(detail=True, methods=["get"])
    def historique(self, request, pk=None):
        """Tout ce qui est arrivé au projet et à ses dossiers (décision 110)."""
        projet = self.get_object()
        return Response(historique_du_projet(projet))

    @extend_schema(responses=ParPaysSerializer)
    @action(detail=False, methods=["get"], url_path="par-pays")
    def par_pays(self, request):
        """Nombre de projets visibles par pays, pour les onglets de la liste.

        Les mêmes filtres que la liste (type, recherche…) sans le pays, que
        l'onglet choisit — comme les dossiers (décision 99).
        """
        projets = self.filter_queryset(self.get_queryset())
        return Response(compter_par_pays(projets, get_access(request.user)))
