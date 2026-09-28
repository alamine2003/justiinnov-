"""Journalisation des bénéficiaires.

Les équipes, projets, intitulés et catégories d'un pays rejoignaient
l'historique ; les bénéficiaires, non. Renommer un fournisseur, changer son
téléphone ou le désactiver ne laissait aucune trace (relevé du 28 septembre
2026) — or c'est à eux que l'argent est versé.
"""

from core.models import ChangeLog
from core.signals import register

from .models import Beneficiary


def connect():
    register(Beneficiary, ChangeLog.Models.BENEFICIARY)
