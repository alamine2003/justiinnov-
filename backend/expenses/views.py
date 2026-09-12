"""Vues des dossiers, dépenses, justificatifs et journal d'audit.

Une vue ne porte que l'adaptation HTTP : le périmètre (``get_object``, 404
hors périmètre), le rôle (``RolePermission``), la lecture de la charge
utile, l'appel du service et la réponse. Les règles du circuit — verrous,
états, quatre yeux, imputation, dépassement, journal — sont dans
``expenses.transitions`` (décision 41).
"""

import logging

from django.db import IntegrityError, transaction
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.db.models import Prefetch
from django.http import FileResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.response import Response

from accounts.permissions import RolePermission, get_access
from accounts.perimetre import filtrer
from accounts.scoping import CountryScopedMixin
from core.journal import Trace
from core.mixins import NoDestroyModelViewSet
from core.regles import traduire_les_regles

from . import stockage, transitions
from .audit import record
from .mixins import DraftDeletableViewSet
from .models import (
    EXPENSE_RELATIONS,
    AuditLog,
    Beneficiary,
    Dossier,
    Expense,
    Proof,
    Rectification,
)
from .serializers import (
    AuditLogSerializer,
    BeneficiarySerializer,
    DossierDetailSerializer,
    DossierSerializer,
    ExpenseRegisterSerializer,
    ExpenseSerializer,
    ExpenseTransitionSerializer,
    ProofReviewSerializer,
    ProofSerializer,
    RectificationDecisionSerializer,
    RectificationSerializer,
    TransitionSerializer,
    TransitionWarningMixin,
)
from .workflow import ACTION_CAPACITES


logger = logging.getLogger(__name__)


class FichierIntrouvable(APIException):
    """La fiche existe, le fichier n'est plus dans le stockage : une anomalie
    grave, jamais un simple 404 — le justificatif est censé être là."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = gettext_lazy(
        "Le fichier de ce justificatif est introuvable dans le stockage : "
        "l'anomalie est journalisée, prévenez l'administrateur."
    )
    default_code = "fichier_introuvable"


class StockageIndisponible(APIException):
    """Le stockage n'a pas répondu : à réessayer, rien n'est perdu."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = gettext_lazy(
        "Le stockage des justificatifs ne répond pas : réessayez dans un instant."
    )
    default_code = "stockage_indisponible"


class DossierTransitionResponseSerializer(TransitionWarningMixin, DossierDetailSerializer):
    """Le dossier après une transition, avec son avertissement éventuel.

    Forme documentaire (schéma) : la vue rend ``presenter()`` et y joint
    ``warning`` ; ce sérialiseur n'est jamais instancié.
    """

    class Meta(DossierDetailSerializer.Meta):
        fields = DossierDetailSerializer.Meta.fields + ["warning"]


class ExpenseTransitionResponseSerializer(TransitionWarningMixin, ExpenseSerializer):
    """La ligne après une transition, avec son avertissement éventuel."""

    class Meta(ExpenseSerializer.Meta):
        fields = ExpenseSerializer.Meta.fields + ["warning"]


def _schema_des_transitions(request, response, *noms):
    """Annotations d'un lot d'actions de workflow : même requête, même réponse."""
    return {nom: extend_schema(request=request, responses=response) for nom in noms}


class WorkflowMixin:
    """Actions de transition : lecture de la charge utile, service, réponse."""

    #: Saisie et circuit : la capacité de chaque action. Modifier un
    #: brouillon est l'écriture par défaut ; créer et supprimer ont la leur.
    write_capability = "expenses.update"
    action_write_capabilities = {
        **ACTION_CAPACITES, "create": "expenses.create", "destroy": "expenses.delete",
    }
    transition_serializer_class = TransitionSerializer

    def perform_transition(self, request, name):
        # Le périmètre d'abord : un objet hors périmètre répond 404 avant
        # que la charge utile ne soit lue. Le rôle a été vérifié par
        # ``RolePermission`` via ``action_write_capabilities``.
        visible = self.get_object()
        serializer = self.transition_serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        with traduire_les_regles():
            resultat = transitions.executer(
                visible, name, get_access(request.user), Trace.depuis_requete(request),
                **serializer.validated_data,
            )
        data = self.presenter(resultat.instance)
        if resultat.warning:
            data = {**data, "warning": resultat.warning}
        return Response(data)

    def presenter(self, instance):
        """Représentation renvoyée une fois la transition acquise."""
        return self.get_serializer(instance).data

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        return self.perform_transition(request, "review")

    @action(detail=True, methods=["post"])
    def justify(self, request, pk=None):
        return self.perform_transition(request, "justify")

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return self.perform_transition(request, "reject")

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        return self.perform_transition(request, "close")


class BeneficiaryViewSet(CountryScopedMixin, NoDestroyModelViewSet):
    """Prospects, clients, fournisseurs et bénéficiaires d'un pays.

    Le référentiel était commun : un pays lisait les fournisseurs et les
    prospects du voisin, de quoi reconstituer qui il démarche et qui il paie.
    Il est cloisonné comme le reste — et tenu par la RH, comme le reste du
    référentiel : le manager choisit un bénéficiaire, il n'en invente pas.
    """

    queryset = Beneficiary.objects.select_related("country").all()
    serializer_class = BeneficiarySerializer
    permission_classes = [RolePermission]
    write_capability = "referentiel.update"
    action_write_capabilities = {"create": "referentiel.create"}
    filterset_fields = ["kind", "is_active", "country"]
    search_fields = ["name", "contact"]
    ordering_fields = ["name", "created_at"]


@extend_schema_view(
    **_schema_des_transitions(
        TransitionSerializer, DossierTransitionResponseSerializer,
        "submit", "review", "justify", "reject", "close", "reopen",
    )
)
class DossierViewSet(WorkflowMixin, CountryScopedMixin, DraftDeletableViewSet):
    """Dossiers de justification (N°ORDRE)."""

    queryset = (
        Dossier.objects.select_related("country", "team", "owner").with_totals()
    )
    permission_classes = [RolePermission]
    filterset_fields = [
        "country", "country__country_ref", "status", "team", "owner",
    ]
    search_fields = ["number", "label"]
    ordering_fields = ["date", "number", "created_at"]
    # Un manager rattaché à des équipes ne voit que leurs dossiers : le
    # cloisonnement par pays ne suffit pas quand plusieurs équipes d'un même
    # pays ne doivent pas lire les dépenses les unes des autres.
    team_lookup = "team"

    #: Actions qui répondent le détail complet (lignes et pièces) : la
    #: fiche, et chaque transition — l'interface affiche le dossier tel
    #: qu'il est après l'action, sans avoir à le recharger.
    ACTIONS_DETAIL = frozenset(
        {"retrieve", "submit", "review", "justify", "reject", "close", "reopen"}
    )

    def get_serializer_class(self):
        if self.action in self.ACTIONS_DETAIL:
            return DossierDetailSerializer
        return DossierSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == "retrieve":
            return self._avec_le_contenu(queryset)
        return queryset

    def _lignes_visibles(self):
        """Lignes d'un dossier, cloisonnées comme la liste des dépenses.

        Un manager rattaché à des équipes ne lit que leurs lignes ; le
        détail d'un dossier ne doit pas lui en montrer davantage que
        ``/api/expenses/``. Le filtre est la primitive unique du périmètre
        (``accounts.perimetre.filtrer``, décision 39), avec les mêmes
        chemins que ``ExpenseViewSet``, appliquée sur la sous-requête du
        prefetch : la règle n'est pas récrite ici.
        """
        return filtrer(
            Expense.objects.select_related(*EXPENSE_RELATIONS).with_rectification(),
            get_access(self.request.user),
            pays=ExpenseViewSet.country_lookup,
            equipe=ExpenseViewSet.team_lookup,
        )

    def _avec_le_contenu(self, queryset):
        """Charge lignes et pièces avec le dossier, en deux requêtes.

        Le détail sérialise chaque ligne avec son contexte : sans
        ``select_related`` sur la sous-requête, chaque ligne rouvrirait une
        requête par relation affichée.
        """
        return queryset.prefetch_related(
            Prefetch("expenses", queryset=self._lignes_visibles()), "proofs"
        )

    def presenter(self, dossier):
        """Le détail complet, relu après la transition.

        L'instance rendue par le service n'a ni annotations ni contenu
        préchargé : la sérialiser telle quelle coûterait une requête par
        ligne. Elle est relue par le queryset du détail — cloisonné,
        annoté, préchargé.
        """
        complet = self._avec_le_contenu(self.get_queryset()).get(pk=dossier.pk)
        return self.get_serializer(complet).data

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        """Déclare le dossier : ses lignes partent avec lui."""
        return self.perform_transition(request, "submit")

    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        """Renvoie un dossier déclaré au brouillon (``transitions.rouvrir``)."""
        return self.perform_transition(request, "reopen")

    def perform_create(self, serializer):
        self._check_country_scope(serializer)
        serializer.save(created_by=self.request.user.username)
        record(self.request, AuditLog.Action.CREATED, serializer.instance)

    def perform_update(self, serializer):
        # Relecture sous verrou : l'instance validée a été lue sans verrou,
        # et une soumission a pu passer entre-temps. Écrire depuis l'objet
        # périmé ramenait le dossier au brouillon sans réouverture ni trace.
        serializer.instance = transitions.verrouiller(serializer.instance)
        with traduire_les_regles():
            transitions.exiger_un_brouillon(serializer.instance)
            transitions.exiger_l_auteur_du_brouillon(
                serializer.instance, get_access(self.request.user)
            )
        super().perform_update(serializer)
        record(self.request, AuditLog.Action.UPDATED, serializer.instance)


@extend_schema_view(
    register=extend_schema(responses=ExpenseRegisterSerializer(many=True)),
    **_schema_des_transitions(
        ExpenseTransitionSerializer, ExpenseTransitionResponseSerializer,
        "review", "justify", "reject", "close",
    ),
)
class ExpenseViewSet(WorkflowMixin, CountryScopedMixin, DraftDeletableViewSet):
    """Lignes de dépenses.

    Pas d'action ``submit`` ici : une ligne ne rejoint qu'un dossier en
    brouillon, et le dossier emporte ses lignes à sa soumission. Une ligne
    ne se déclare donc jamais seule.
    """

    # ``with_rectification`` : ``allowed_actions`` dit si une rectification
    # peut être demandée sans une requête par ligne.
    queryset = Expense.objects.select_related(*EXPENSE_RELATIONS).with_rectification()
    serializer_class = ExpenseSerializer
    transition_serializer_class = ExpenseTransitionSerializer
    permission_classes = [RolePermission]
    # Forme étendue : le §5.6 demande de filtrer par période et par état
    # multiple, ce qu'une simple liste de champs ne permet pas.
    filterset_fields = {
        "country": ["exact"],
        "country__country_ref": ["exact"],
        "dossier": ["exact"],
        "dossier__number": ["exact"],
        "status": ["exact", "in"],
        "team": ["exact"],
        "owner": ["exact"],
        "project": ["exact"],
        "beneficiary": ["exact"],
        "expense_title": ["exact"],
        "marketing_category": ["exact"],
        "payment_method": ["exact"],
        "date": ["gte", "lte"],
    }
    search_fields = ["title", "place", "description", "dossier__number"]
    ordering_fields = ["date", "amount", "created_at"]
    # Même cloisonnement par équipe que le dossier : le registre et les
    # filtres passent par ce queryset, ils en héritent.
    team_lookup = "team"

    @action(detail=False, methods=["get"])
    def register(self, request):
        """Registre de justification : chaque dépense avec ses preuves.

        Le journal d'audit dit qui a fait quoi ; ce registre dit où est passé
        l'argent et ce qui l'atteste.
        """
        queryset = self.filter_queryset(
            self.get_queryset().prefetch_related("dossier__proofs")
        )
        page = self.paginate_queryset(queryset)
        # Le contexte porte la requête : sans elle, ``allowed_actions`` ne
        # saurait pas pour qui il calcule.
        serializer = ExpenseRegisterSerializer(
            page if page is not None else queryset, many=True,
            context=self.get_serializer_context(),
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def perform_create(self, serializer):
        """Enregistre une ligne, si son dossier l'accepte encore.

        Le contrôle du dossier vient après celui du périmètre, et non dans le
        sérialiseur : dire « ce dossier est déjà soumis » à quelqu'un qui n'a
        pas le droit de le voir révélerait son existence et son état.
        """
        self._check_country_scope(serializer)
        # Le dossier est verrouillé le temps de l'insertion : une soumission
        # ou un retrait du dossier au même instant attend, puis trouve la
        # ligne — au lieu d'une ligne en brouillon dans un dossier déclaré
        # que rien ne soumettrait plus, ou d'un retrait qui bute (§3.7, §4.4).
        with traduire_les_regles():
            transitions.exiger_un_dossier_ouvert(
                transitions.verrouiller_le_dossier_vise(
                    serializer.validated_data.get("dossier"), None
                )
            )
        serializer.save(created_by=self.request.user.username)
        record(self.request, AuditLog.Action.CREATED, serializer.instance)

    def perform_update(self, serializer):
        self._check_country_scope(serializer)
        # Relecture sous verrou : l'instance validée a été lue sans verrou,
        # et une soumission a pu passer entre-temps. Écrire depuis l'objet
        # périmé ramenait la ligne au brouillon, sans imputation, sans
        # réouverture ni trace — la seule exception à l'irréversibilité
        # contournée par un double clic.
        # Le dossier d'abord, la ligne ensuite : le même ordre que la
        # soumission, qui verrouille le dossier puis ses lignes — l'ordre
        # inverse pouvait s'interbloquer. Déplacer un brouillon vers un
        # dossier déjà déclaré l'y perdrait, exactement comme l'y créer.
        dossier_vise = transitions.verrouiller_le_dossier_vise(
            serializer.validated_data.get("dossier"), serializer.instance
        )
        serializer.instance = transitions.verrouiller(serializer.instance)
        with traduire_les_regles():
            transitions.exiger_un_brouillon(serializer.instance)
            transitions.exiger_l_auteur_du_brouillon(
                serializer.instance, get_access(self.request.user)
            )
            transitions.exiger_un_dossier_ouvert(dossier_vise)
        stored = serializer.instance
        previous = {
            "amount": str(stored.amount),
            "justified_amount": str(stored.justified_amount),
        }
        serializer.save()
        record(
            self.request,
            AuditLog.Action.UPDATED,
            serializer.instance,
            before=previous,
            after={
                "amount": str(serializer.instance.amount),
                "justified_amount": str(serializer.instance.justified_amount),
            },
        )


@extend_schema_view(
    # Le dépôt est un envoi de fichier : la forme JSON n'a pas de sens ici.
    create=extend_schema(request={"multipart/form-data": ProofSerializer}),
    review=extend_schema(request=ProofReviewSerializer, responses=ProofSerializer),
    download=extend_schema(
        responses={(200, "application/octet-stream"): OpenApiTypes.BINARY}
    ),
)
class ProofViewSet(CountryScopedMixin, NoDestroyModelViewSet):
    """Pièces justificatives, rattachées au dossier."""

    queryset = Proof.objects.select_related("dossier__country").all()
    serializer_class = ProofSerializer
    permission_classes = [RolePermission]
    filterset_fields = ["dossier", "kind", "status", "is_complete"]
    search_fields = ["original_name", "dossier__number"]
    ordering_fields = ["created_at", "version"]
    # La preuve n'a pas de pays propre : elle suit celui de son dossier —
    # et son équipe de même.
    country_lookup = "dossier__country"
    country_field = None
    country_via = "dossier"
    team_lookup = "dossier__team"
    # Le contrôle documentaire relève du siège (DF), pas du déposant.
    write_capability = "proofs.upload"
    action_write_capabilities = {"review": "proofs.review"}

    def create(self, request, *args, **kwargs):
        """Dépose une pièce ; un échec ne laisse pas son fichier derrière lui.

        ``FileField`` écrit le fichier dans le stockage **avant** l'``INSERT``,
        et l'écriture du fichier n'a pas de retour arrière : si la
        transaction de la vue est ensuite annulée — trace d'audit
        impossible, contrainte sur la pièce remplacée, verrou du dossier
        perdu — la fiche disparaît et le fichier reste. Il est retiré ici,
        après la sortie du bloc transactionnel, sur le chemin d'erreur
        (audit du 8 septembre 2026, §4.4 ; le cas du seul ``INSERT`` refusé
        est traité dans ``ProofSerializer.create``).
        """
        with stockage.suivre_les_depots() as deposes:
            try:
                return super().create(request, *args, **kwargs)
            except Exception:
                for nom in deposes:
                    stockage.effacer_nom_sans_bruit(nom)
                raise

    @transaction.atomic
    def perform_create(self, serializer):
        self._check_country_scope(serializer)
        # Le dossier sous verrou le temps du dépôt : un retrait du brouillon
        # au même instant attend, puis la pièce ne trouve plus son dossier
        # (404) au lieu d'une violation de clé étrangère ; une clôture au
        # même instant est relue avant d'écrire.
        with traduire_les_regles():
            dossier = transitions.verrouiller_le_dossier_vise(
                serializer.validated_data["dossier"], None
            )
        if dossier.status in transitions.PROOF_LOCKED_STATUSES:
            raise ValidationError(
                _("Le dossier est clôturé : plus aucun justificatif ne peut y être ajouté.")
            )
        serializer.validated_data["dossier"] = dossier
        replaced = serializer.validated_data.get("replaces")
        if replaced is not None:
            # Revalidé ici, hors sérialiseur : la pièce remplacée change
            # d'état, elle doit relever du même dossier que la nouvelle.
            ProofSerializer.verifier_le_remplacement(replaced, dossier)
            replaced = Proof.objects.select_for_update().get(pk=replaced.pk)
        try:
            serializer.save(
                uploaded_by=self.request.user.username,
                version=replaced.version + 1 if replaced else 1,
            )
        except IntegrityError as exc:
            # Deux dépôts simultanés du même fichier : la base a tranché.
            raise ValidationError(
                {"file": [_("Ce fichier est déjà rattaché à ce dossier (doublon).")]}
            ) from exc
        proof = serializer.instance
        if replaced is not None:
            replaced.status = Proof.ProofStatus.ARCHIVED
            replaced.save(update_fields=["status", "updated_at"])
            record(
                self.request,
                AuditLog.Action.PROOF_REPLACED,
                proof,
                country=dossier.country,
                dossier=dossier.number,
                sha256=proof.sha256,
                version=proof.version,
                before={"sha256": replaced.sha256, "version": replaced.version},
                after={"sha256": proof.sha256, "version": proof.version},
                replaces=replaced.pk,
            )
            return
        record(
            self.request,
            AuditLog.Action.PROOF_UPLOADED,
            proof,
            country=dossier.country,
            dossier=dossier.number,
            sha256=proof.sha256,
            version=proof.version,
        )

    def perform_update(self, serializer):
        self._check_country_scope(serializer)
        avant = {"kind": serializer.instance.kind}
        serializer.save()
        record(
            self.request,
            AuditLog.Action.UPDATED,
            serializer.instance,
            country=serializer.instance.dossier.country,
            before=avant,
            after={"kind": serializer.instance.kind},
        )

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        """Contrôle documentaire (``transitions.controler_piece``)."""
        visible = self.get_object()
        serializer = ProofReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with traduire_les_regles():
            resultat = transitions.controler_piece(
                visible,
                serializer.validated_data["status"],
                get_access(request.user),
                motif=serializer.validated_data.get("reason", ""),
                trace=Trace.depuis_requete(request),
            )
        return Response(self.get_serializer(resultat.instance).data)

    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """Téléchargement contrôlé (§5.4).

        Le fichier transite par cette vue plutôt que par une URL signée : le
        périmètre est ainsi vérifié à chaque accès, et chaque téléchargement
        laisse une trace d'audit. Il est servi en flux : ``FileResponse``
        lit le fichier ouvert par blocs, sans le charger en mémoire — une
        pièce de vingt mégaoctets ne doit pas en coûter vingt au serveur.
        """
        proof = self.get_object()
        # Le fichier d'abord, la trace ensuite : une entrée « téléchargé »
        # écrite avant l'ouverture attestait d'un téléchargement qui n'avait
        # pas eu lieu quand l'objet manquait dans le stockage. La trace dit
        # que le serveur a **servi** le fichier — pas que le client l'a
        # reçu en entier, ce qu'aucun serveur ne peut attester.
        try:
            contenu = proof.file.open("rb")
        except FileNotFoundError as exc:
            logger.error(
                "Justificatif %s (%s) introuvable dans le stockage : %s",
                proof.pk, proof.file.name, exc,
            )
            raise FichierIntrouvable() from exc
        except Exception as exc:
            logger.exception("Stockage des justificatifs injoignable (%s)", proof.file.name)
            raise StockageIndisponible() from exc
        record(
            request,
            AuditLog.Action.DOWNLOADED,
            proof,
            country=proof.dossier.country,
            sha256=proof.sha256,
        )
        return FileResponse(
            contenu,
            as_attachment=True,
            filename=proof.original_name or proof.file.name.rsplit("/", 1)[-1],
            content_type=proof.content_type or None,
        )


class RectificationViewSet(
    CountryScopedMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """Demandes de rectification d'un constat (``transitions``).

    Une demande ne se réécrit pas : elle se dépose, puis s'approuve ou se
    refuse. ``PUT``, ``PATCH`` et ``DELETE`` répondent 405 : un motif
    changé après la décision ferait mentir le journal. Le périmètre est
    celui de la ligne visée — pays, et équipes pour un manager qui y est
    restreint — : une demande hors périmètre n'existe pas (404).
    """

    queryset = Rectification.objects.select_related(
        "expense__country", "expense__dossier", "expense__team"
    ).all()
    serializer_class = RectificationSerializer
    permission_classes = [RolePermission]
    write_capability = "rectifications.decide"
    action_write_capabilities = {"create": "rectifications.request"}
    filterset_fields = ["status", "expense", "expense__dossier", "expense__country"]
    ordering_fields = ["created_at", "decided_at"]
    country_lookup = "expense__country"
    team_lookup = "expense__team"
    country_field = None

    def perform_create(self, serializer):
        donnees = serializer.validated_data
        with traduire_les_regles():
            resultat = transitions.demander_rectification(
                donnees["expense"], get_access(self.request.user),
                donnees["motif"], Trace.depuis_requete(self.request),
            )
        serializer.instance = resultat.instance

    def _decider(self, request, service):
        """Approbation ou refus : périmètre, motif, service, réponse."""
        visible = self.get_object()
        serializer = RectificationDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with traduire_les_regles():
            resultat = service(
                visible, get_access(request.user),
                serializer.validated_data.get("note", ""),
                Trace.depuis_requete(request),
            )
        # Relue par le queryset : la décision a changé la ligne et le
        # dossier, et la réponse doit les montrer tels qu'ils sont.
        return Response(self.get_serializer(self.get_queryset().get(pk=resultat.instance.pk)).data)

    @extend_schema(request=RectificationDecisionSerializer, responses=RectificationSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Approuve : la ligne revient en contrôle, le dossier la suit."""
        return self._decider(request, transitions.approuver_rectification)

    @extend_schema(request=RectificationDecisionSerializer, responses=RectificationSerializer)
    @action(detail=True, methods=["post"])
    def refuse(self, request, pk=None):
        """Refuse : le constat tient. Le motif est obligatoire."""
        return self._decider(request, transitions.refuser_rectification)


class AuditLogViewSet(CountryScopedMixin, viewsets.ReadOnlyModelViewSet):
    """Journal d'audit — consultation par la RH, qui audite, et la direction.

    Le DM et le DF n'y ont pas accès : le journal relit leurs propres
    décisions, et cette relecture est un acte d'administration.
    """

    queryset = AuditLog.objects.select_related("country").all()
    serializer_class = AuditLogSerializer
    permission_classes = [RolePermission]
    read_capability = "audit.read"
    filterset_fields = ["user", "action", "object_type", "country"]
    search_fields = ["label", "user"]
    ordering_fields = ["created_at"]
