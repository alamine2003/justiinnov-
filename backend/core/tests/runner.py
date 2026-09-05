"""Lanceur de tests : rend au cache l'isolation que la transaction lui donnait.

Sous les réglages de test (``config.settings``), le cache est en mémoire.
Il survit donc à la transaction que Django annule après chaque test, alors
que le cache en base partait avec elle : compteurs de débit et configuration
du circuit fuiraient d'un test au suivant — un ``429`` au dixième test qui
se connecte, une politique de dépassement modifiée par un test et lue par un
autre. Le vider au ``startTest`` de chaque test, avant ``setUp``, rétablit
l'isolation sans que chaque classe ait à y penser.

La vidange est posée sur la classe de résultat, seul objet que les deux
modes traversent : en série, celle du lanceur ``unittest`` ; sous
``--parallel``, celle que chaque processus instancie pour rejouer sa part
(``RemoteTestRunner``), qui a par ailleurs son propre cache mémoire.
"""

import unittest

from django.core.cache import cache
from django.test.runner import (
    DiscoverRunner,
    ParallelTestSuite,
    RemoteTestResult,
    RemoteTestRunner,
)


class VidangeDuCache:
    """À mêler à une classe de résultat ``unittest``."""

    def startTest(self, test):
        cache.clear()
        super().startTest(test)


class ResultatDistant(VidangeDuCache, RemoteTestResult):
    pass


class LanceurDistant(RemoteTestRunner):
    resultclass = ResultatDistant


class SuiteParallele(ParallelTestSuite):
    runner_class = LanceurDistant


class LanceurDeTests(DiscoverRunner):
    parallel_test_suite = SuiteParallele

    def get_resultclass(self):
        base = super().get_resultclass() or unittest.TextTestResult
        return type("Resultat", (VidangeDuCache, base), {})
