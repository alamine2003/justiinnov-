"""Services de la double authentification, appelés sans passer par HTTP.

L'état TOTP du profil se modifie dans ``accounts.totp`` (décision 124) ;
les vues ne font que répondre et tracer. Ces tests appellent les services
directement, comme le ferait une commande.
"""

from datetime import timedelta

import pyotp
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token

from accounts import totp
from accounts.authentication import obtenir_jeton
from accounts.models import Role, UserProfile
from core.regles import RegleViolee

from .test_scoping import make_user


def _code(secret, minutes=0):
    return pyotp.TOTP(secret).at(timezone.now() + timedelta(minutes=minutes))


class ConnexionTests(TestCase):
    def test_compte_non_enrole_passe_sans_code(self):
        user = make_user("libre.innov", Role.MANAGER, totp_confirmed=False)
        self.assertIsNone(totp.verifier_a_la_connexion(user.profile, None))
        self.assertIsNone(totp.verifier_a_la_connexion(None, None))

    def test_compte_enrole_code_requis_puis_consomme_une_fois(self):
        profile = make_user("enrole.innov", Role.ADMIN).profile
        self.assertEqual(totp.verifier_a_la_connexion(profile, ""), totp.CODE_REQUIS)
        self.assertEqual(totp.verifier_a_la_connexion(profile, None), totp.CODE_REQUIS)
        self.assertEqual(
            totp.verifier_a_la_connexion(profile, _code(profile.totp_secret, -5)),
            totp.CODE_INVALIDE,
        )
        code = _code(profile.totp_secret)
        self.assertIsNone(totp.verifier_a_la_connexion(profile, code))
        # Rejoué, le même code est refusé.
        self.assertEqual(totp.verifier_a_la_connexion(profile, code), totp.CODE_INVALIDE)


class EnrolementTests(TestCase):
    def test_enroler_pose_un_secret_non_confirme(self):
        user = make_user("neuf.innov", Role.MANAGER, totp_confirmed=False)
        profile = user.profile
        profile.totp_last_counter = 12
        profile.save(update_fields=["totp_last_counter"])

        secret = totp.enroler(profile)

        profile = UserProfile.objects.get(pk=profile.pk)
        self.assertEqual(profile.totp_secret, secret)
        self.assertIsNone(profile.totp_last_counter)
        self.assertFalse(profile.totp_confirmed)

    def test_un_compte_confirme_ne_se_reenrole_pas(self):
        profile = make_user("actif.innov", Role.MANAGER).profile
        secret = profile.totp_secret
        with self.assertRaises(RegleViolee) as refus:
            totp.enroler(profile)
        self.assertEqual(refus.exception.champ, "detail")
        self.assertEqual(UserProfile.objects.get(pk=profile.pk).totp_secret, secret)

    def test_confirmer(self):
        profile = make_user("confirme.innov", Role.MANAGER, totp_confirmed=False).profile
        with self.assertRaises(RegleViolee):
            totp.confirmer(profile, "123456")  # aucun enrôlement en cours
        secret = totp.enroler(profile)

        self.assertFalse(totp.confirmer(profile, _code(secret, -5)))
        self.assertFalse(UserProfile.objects.get(pk=profile.pk).totp_confirmed)

        code = _code(secret)
        self.assertTrue(totp.confirmer(profile, code))
        profile = UserProfile.objects.get(pk=profile.pk)
        self.assertTrue(profile.totp_confirmed)
        # Le code de confirmation ne resservira pas à la connexion.
        self.assertEqual(totp.verifier_a_la_connexion(profile, code), totp.CODE_INVALIDE)
        with self.assertRaises(RegleViolee):
            totp.confirmer(profile, _code(secret))


class ReinitialisationTests(TestCase):
    def test_reinitialiser_efface_l_enrolement_et_le_jeton(self):
        user = make_user("perdu.innov", Role.MANAGER)
        obtenir_jeton(user)
        profile = user.profile

        self.assertTrue(totp.reinitialiser(profile))

        profile = UserProfile.objects.get(pk=profile.pk)
        self.assertEqual(profile.totp_secret, "")
        self.assertIsNone(profile.totp_confirmed_at)
        self.assertIsNone(profile.totp_last_counter)
        self.assertFalse(Token.objects.filter(user=user).exists())
        # Une seconde fois : il n'était plus confirmé.
        self.assertFalse(totp.reinitialiser(profile))
