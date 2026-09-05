"""Enveloppes budgétaires, réallocations et taux de change.

Une enveloppe est annuelle et rattachée à un pays. Elle peut être déclinée en
sous-enveloppes par projet (``project`` renseigné). Les montants sont stockés
dans la devise du pays ; la consolidation au siège se fait en FCFA (XOF).
"""

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy

from accounts.perimetre import filtrer
from accounts.permissions import get_access
from core.models import Country, Manager, Project, Team, TimeStampedModel
from core.statuts import CONSUMING_STATUSES, ENGAGING_STATUSES

#: Devise de consolidation : le siège est au Sénégal.
CONSOLIDATION_CURRENCY = "XOF"


class OverrunPolicy(models.TextChoices):
    """Conduite à tenir lorsqu'une dépense ferait dépasser l'enveloppe (§6)."""

    BLOCK = "block", _("Bloquer")
    WARN = "warn", _("Alerter")
    APPROVAL = "approval", _("Soumettre à approbation")


def default_overrun_policy():
    """Politique utilisée par une nouvelle enveloppe sans choix explicite.

    **Conservée pour la migration ``0003_default_overrun_policy``**, qui la
    référence comme défaut du champ dans son état historique : la retirer
    casserait le rejeu des migrations. Le code courant ne l'appelle plus —
    la résolution depuis la configuration du circuit se fait dans le
    sérialiseur, à la création par l'API — et le champ porte un défaut
    **littéral** : un défaut calculé lirait la configuration à chaque
    instanciation, y compris hors requête.
    """
    from core.models import WorkflowConfiguration

    return WorkflowConfiguration.charger().default_overrun_policy


class BudgetQuerySet(models.QuerySet):
    def visible_par(self, user):
        """Enveloppes du périmètre de l'utilisateur.

        Le pays est porté par l'enveloppe elle-même : filtrer dessus ne
        multiplie aucune ligne, contrairement au ``distinct()`` générique de
        ``CountryScopedMixin`` qui, combiné aux agrégats de
        :meth:`with_consumption`, produirait un DISTINCT sur un GROUP BY.
        Sert aussi à borner les champs « enveloppe » des sérialiseurs : une
        enveloppe hors périmètre y est simplement « invalide », sans révéler
        qu'elle existe.
        """
        return filtrer(self, get_access(user))

    def with_consumption(self):
        """Annote engagé, consommé et justifié en une seule requête.

        Les trois totaux passent par la même jointure sur les dépenses, avec
        des filtres conditionnels : pas de multiplication des lignes possible,
        `expenses` étant l'unique relation jointe.
        """
        money = models.DecimalField(max_digits=16, decimal_places=2)
        engaging = list(ENGAGING_STATUSES)
        consuming = list(CONSUMING_STATUSES)
        zero = Value(Decimal("0.00"))
        # L'agrégation introduit un GROUP BY, qui fait perdre à Django
        # l'ordre par défaut du modèle : sans tri explicite, deux pages
        # successives pourraient se recouvrir.
        return self.order_by(*Budget._meta.ordering).annotate(
            engaged_total=Coalesce(
                Sum("expenses__amount", filter=Q(expenses__status__in=engaging)),
                zero,
                output_field=money,
            ),
            consumed_total=Coalesce(
                Sum("expenses__amount", filter=Q(expenses__status__in=consuming)),
                zero,
                output_field=money,
            ),
            justified_total=Coalesce(
                Sum(
                    "expenses__justified_amount",
                    filter=Q(expenses__status__in=consuming),
                ),
                zero,
                output_field=money,
            ),
        )


class Budget(TimeStampedModel):
    """Enveloppe annuelle d'un pays, ou sous-enveloppe d'un projet."""

    objects = BudgetQuerySet.as_manager()

    # ``PROTECT`` partout : une enveloppe porte de l'argent et des dépenses.
    # La supprimer en cascade avec son pays ou son projet effacerait des
    # montants sans trace ; le référentiel se désactive, il ne se supprime pas.
    country = models.ForeignKey(
        Country, on_delete=models.PROTECT, related_name="budgets", verbose_name=_("Pays")
    )
    year = models.PositiveIntegerField(_("Année"))
    # Une sous-enveloppe découpe l'enveloppe du pays selon **une** dimension :
    # un projet, une équipe ou un manager. En autoriser plusieurs à la fois
    # rendrait l'imputation d'une dépense ambiguë.
    project = models.ForeignKey(
        Project,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="budgets",
        verbose_name=_("Projet"),
    )
    team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="budgets",
        verbose_name=_("Équipe"),
    )
    manager = models.ForeignKey(
        Manager,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="budgets",
        verbose_name=_("Manager"),
    )
    amount = models.DecimalField(
        _("Montant"),
        max_digits=16,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    overrun_policy = models.CharField(
        _("Politique de dépassement"),
        max_length=20,
        choices=OverrunPolicy.choices,
        default=OverrunPolicy.BLOCK,
    )
    is_active = models.BooleanField(_("Actif"), default=True)

    class Meta:
        # ``-pk`` en dernier : deux enveloppes du même pays et de la même
        # année (sous-enveloppes) auraient sinon un ordre indéterminé, et la
        # pagination pourrait en montrer une deux fois ou en sauter une.
        ordering = ["-year", "country__name", "-pk"]
        verbose_name = _("Budget")
        indexes = [
            # Le tableau de bord et la liste filtrent toujours ainsi.
            models.Index(
                fields=["country", "year", "is_active"],
                name="budget_pays_annee_actif",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gte=0), name="budget_montant_positif_ou_nul"
            ),
            models.UniqueConstraint(
                fields=["country", "year"],
                condition=Q(
                    project__isnull=True, team__isnull=True, manager__isnull=True
                ),
                name="unique_enveloppe_pays_annee",
            ),
            models.UniqueConstraint(
                fields=["country", "project", "year"],
                name="unique_sous_enveloppe_projet_annee",
            ),
            models.UniqueConstraint(
                fields=["country", "team", "year"],
                name="unique_sous_enveloppe_equipe_annee",
            ),
            models.UniqueConstraint(
                fields=["country", "manager", "year"],
                name="unique_sous_enveloppe_manager_annee",
            ),
            models.CheckConstraint(
                condition=(
                    Q(project__isnull=True, team__isnull=True, manager__isnull=True)
                    | Q(project__isnull=False, team__isnull=True, manager__isnull=True)
                    | Q(project__isnull=True, team__isnull=False, manager__isnull=True)
                    | Q(project__isnull=True, team__isnull=True, manager__isnull=False)
                ),
                name="sous_enveloppe_une_seule_dimension",
            ),
        ]

    def __str__(self):
        scope = self.scope_label
        if scope:
            return f"{self.country.name} {self.year} — {scope}"
        return f"{self.country.name} {self.year}"

    @property
    def scope_label(self):
        """Dimension découpée, ou ``None`` pour l'enveloppe du pays."""
        if self.project_id:
            return self.project.name
        if self.team_id:
            return _("Équipe {name}").format(name=self.team.name)
        if self.manager_id:
            return _("Manager {name}").format(name=self.manager.name)
        return None

    @property
    def scope_kind(self):
        if self.project_id:
            return "project"
        if self.team_id:
            return "team"
        if self.manager_id:
            return "manager"
        return "country"

    @property
    def currency(self):
        return self.country.currency


class BudgetReallocation(TimeStampedModel):
    """Transfert entre enveloppes, avec justification et approbation (§5.2)."""

    class Status(models.TextChoices):
        PENDING = "pending", _("En attente")
        APPROVED = "approved", _("Approuvée")
        REJECTED = "rejected", _("Refusée")

    source = models.ForeignKey(
        Budget, on_delete=models.PROTECT, related_name="reallocations_out",
        verbose_name=_("Enveloppe source"),
    )
    target = models.ForeignKey(
        Budget, on_delete=models.PROTECT, related_name="reallocations_in",
        verbose_name=_("Enveloppe destinataire"),
    )
    amount = models.DecimalField(
        _("Montant"),
        max_digits=16,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    reason = models.TextField(_("Justification"))
    status = models.CharField(
        _("Statut"), max_length=20, choices=Status.choices, default=Status.PENDING
    )
    requested_by = models.CharField(_("Demandée par"), max_length=180, blank=True)
    decided_by = models.CharField(_("Décidée par"), max_length=180, blank=True)
    decided_at = models.DateTimeField(_("Décidée le"), null=True, blank=True)
    decision_note = models.TextField(_("Motif de la décision"), blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = _("Réallocation budgétaire")
        verbose_name_plural = _("Réallocations budgétaires")
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="reallocation_montant_positif"
            ),
            models.CheckConstraint(
                condition=~Q(source=models.F("target")),
                name="reallocation_source_differente_cible",
            ),
            # Une décision sans date n'est pas une décision : le journal doit
            # pouvoir dire *quand* le transfert a été tranché.
            models.CheckConstraint(
                condition=Q(status="pending") | Q(decided_at__isnull=False),
                name="reallocation_decision_datee",
            ),
        ]

    def __str__(self):
        return f"{self.amount} : {self.source} → {self.target}"


class ExchangeRate(models.Model):
    """Taux de conversion d'une devise vers le FCFA, daté.

    La conversion d'une opération est figée au taux en vigueur à sa date, afin
    que les rapports historiques restent stables.
    """

    currency = models.CharField(_("Devise"), max_length=3, help_text=_("ISO 4217"))
    rate_to_xof = models.DecimalField(
        _("Taux vers le FCFA"),
        max_digits=18,
        decimal_places=6,
        validators=[MinValueValidator(Decimal("0.000001"))],
        help_text=_("Nombre de FCFA pour une unité de la devise."),
    )
    valid_from = models.DateField(_("En vigueur depuis"))
    created_at = models.DateTimeField(_("Créé le"), auto_now_add=True)

    class Meta:
        ordering = ["currency", "-valid_from", "-pk"]
        verbose_name = _("Taux de change")
        verbose_name_plural = pgettext_lazy("pluriel", "Taux de change")
        constraints = [
            models.UniqueConstraint(
                fields=["currency", "valid_from"], name="unique_taux_devise_date"
            ),
            # Un taux nul ferait disparaître un montant du consolidé, un taux
            # négatif l'inverserait : la base le refuse, pas seulement l'API.
            models.CheckConstraint(
                condition=Q(rate_to_xof__gt=0), name="taux_strictement_positif"
            ),
        ]

    def __str__(self):
        return f"1 {self.currency} = {self.rate_to_xof} XOF ({self.valid_from})"
