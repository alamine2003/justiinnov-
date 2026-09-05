"""Configuration Django pour :attr:`config`.

La gestion des pays et organisations (section 5.1) est fournie par
l'application :mod:`core`.
"""

import os
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# Le mode debug doit être un choix explicite : par défaut, on est en production.
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY est obligatoire hors mode debug."
        )
    SECRET_KEY = "django-insecure-dev-only-change-me-in-production"

ALLOWED_HOSTS = [
    h
    for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h
]
# Le contrôle de santé du conteneur interroge le serveur sur sa propre
# boucle locale : sans cette entrée, il répondrait 400 en production, où
# seul le domaine public est déclaré — et Docker déclarerait mort un backend
# en parfaite santé.
if "127.0.0.1" not in ALLOWED_HOSTS and "*" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("127.0.0.1")
# Prometheus interroge ``/metrics`` par le nom du service sur le réseau
# interne de la pile : ce nom n'est pas un domaine public, il doit pourtant
# être accepté.
if "backend" not in ALLOWED_HOSTS and "*" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("backend")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # libs
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "corsheaders",
    # Métriques HTTP et base pour Prometheus (tableau de bord Grafana).
    "django_prometheus",
    # Schéma OpenAPI (``/api/schema/``, ``manage.py spectacular``).
    "drf_spectacular",
    # apps
    "core",
    "accounts",
    "budget",
    "expenses",
    "notifications",
    "reporting",
]

MIDDLEWARE = [
    # Mesure chaque requête de bout en bout : premier et dernier de la pile.
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    # Choisit la langue des messages d'après ``Accept-Language`` (interface
    # bilingue). Après la session, avant le reste.
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # Après l'authentification de session, avant toute vue : un compte au
    # mot de passe provisoire ne doit rien pouvoir faire d'autre que le
    # changer.
    "accounts.middleware.ProvisionalPasswordMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Expose la requête courante à l'historisation (auteur, adresse IP).
    "core.middleware.CurrentRequestMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Cache partagé entre les workers gunicorn. Indispensable pour la limitation
# de débit : un cache local à chaque processus multiplierait la limite par le
# nombre de workers.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
    }
}



def parse_database_url(url):
    """Traduit une URL ``postgresql://`` en configuration Django.

    Fonction pure, sans dépendance (ni dj-database-url ni django-environ) :
    on garde la main sur ce qui est transmis à psycopg. Les paramètres de la
    chaîne de requête (``sslmode``, ``channel_binding``, ``options``…) vont
    tels quels dans ``OPTIONS``, sans liste blanche : ce sont ceux de libpq.
    Utilisateur et mot de passe sont décodés, un mot de passe pouvant
    contenir ``@``, ``/`` ou ``%`` encodés.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("postgres", "postgresql"):
        raise ImproperlyConfigured(
            "DATABASE_URL doit commencer par postgresql:// "
            f"(reçu : {parsed.scheme or 'aucun schéma'})."
        )
    name = unquote(parsed.path.lstrip("/"))
    if not name:
        raise ImproperlyConfigured("DATABASE_URL ne nomme aucune base (chemin vide).")
    config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": name,
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port) if parsed.port else "",
    }
    options = dict(parse_qsl(parsed.query, keep_blank_values=False))
    if options:
        config["OPTIONS"] = options
    return config


# Connexions réutilisées entre requêtes, et vérifiées avant usage : sans
# contrôle, une connexion coupée par Postgres ou le réseau ne se découvre
# qu'à la première requête qui échoue.
_DATABASE_COMMON = {"CONN_MAX_AGE": 60, "CONN_HEALTH_CHECKS": True}

# `DATABASE_URL` (base hébergée, TLS imposé) prime sur les variables
# POSTGRES_* ; sans elle, on lit ces dernières, qui sont celles de la pile
# Docker. Voir deploy/.env.example.
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL:
    DATABASES = {"default": {**parse_database_url(DATABASE_URL), **_DATABASE_COMMON}}
else:
    POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "")
    if not POSTGRES_PASSWORD:
        if not DEBUG:
            # Même exigence que pour la clé secrète : un mot de passe de
            # développement ne doit pas pouvoir servir en production par oubli.
            raise ImproperlyConfigured(
                "POSTGRES_PASSWORD (ou DATABASE_URL) est obligatoire hors mode debug."
            )
        POSTGRES_PASSWORD = "justi"

    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB", "justi_innov"),
            "USER": os.environ.get("POSTGRES_USER", "justi"),
            "PASSWORD": POSTGRES_PASSWORD,
            "HOST": os.environ.get("POSTGRES_HOST", "db"),
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
            **_DATABASE_COMMON,
        }
    }

# ---------------------------------------------------------------------------
# Authentification REST
# ---------------------------------------------------------------------------
# Durée de vie d'un jeton, en jours (0 : illimitée). Un jeton DRF n'expire
# jamais de lui-même ; celui d'un poste oublié resterait valable des années.
TOKEN_MAX_AGE_DAYS = int(os.environ.get("TOKEN_MAX_AGE_DAYS", "30"))

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # Jeton à durée de vie bornée, profil chargé d'emblée, résultat du
        # middleware réutilisé (cf. accounts.authentication).
        "accounts.authentication.JetonAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # L'API navigable n'a sa place qu'en développement : en production, elle
    # rend des formulaires HTML et révèle la forme des ressources à qui tombe
    # sur une URL.
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ] + (["rest_framework.renderers.BrowsableAPIRenderer"] if DEBUG else []),
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "SEARCH_PARAM": "search",
    # Pas de limite anonyme globale : hors obtention du jeton, tout répond 401
    # aux anonymes, et la limite ne ferait que compter des refus. Le point de
    # santé, interrogé toutes les trente secondes, la déclenchait.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
    ],
    # ``login`` (par adresse) et ``login_user`` (par nom de compte) protègent
    # l'obtention du jeton (cf. accounts.views).
    "DEFAULT_THROTTLE_RATES": {
        "user": "2000/hour",
        "login": "10/min",
        "login_user": "5/min",
    },
    # Nombre de mandataires de confiance devant Django (nginx, Caddy…) : sert
    # à lire l'adresse réelle du client dans X-Forwarded-For, pour le journal
    # et la limitation de débit. Zéro : seule REMOTE_ADDR fait foi.
    "NUM_PROXIES": int(os.environ.get("DJANGO_NUM_PROXIES", "0")),
    # Le contrat d'API est déduit des vues et des sérialiseurs, jamais écrit
    # à la main : ``docs/api/schema.json`` et les types du frontend en
    # dérivent (voir README, « API REST »).
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# ---------------------------------------------------------------------------
# Schéma OpenAPI
# ---------------------------------------------------------------------------
# Servi sur ``/api/schema/`` aux rôles du siège (config/schema.py) ; généré
# hors ligne par ``manage.py spectacular`` pour ``docs/api/schema.json``,
# dont ``frontend/scripts/generer-types.mts`` tire les types TypeScript. Les
# réglages figent la forme du document : la CI compare une génération
# fraîche au fichier versionné, deux générations doivent être identiques.
SPECTACULAR_SETTINGS = {
    "TITLE": "JUSTI INNOV",
    "DESCRIPTION": (
        "Plateforme de contrôle budgétaire : suivi des dépenses de pays "
        "africains et de leurs justificatifs. Le pays déclare, le siège "
        "constate ; une dépense soumise est irréversible ; rien ne se "
        "supprime hors brouillon ; les chiffres se calculent côté serveur.\n\n"
        "Authentification par jeton (`Authorization: Token <jeton>`), obtenu "
        "sur `/api/token-auth/`. Toute liste est paginée (`page`, "
        "`page_size`) et filtrée par le périmètre du compte : un objet hors "
        "périmètre répond 404. Les messages suivent `Accept-Language` "
        "(`fr` par défaut, `en`)."
    ),
    "VERSION": "1.0.0",
    # Le document n'est pas servi par la vue livrée avec drf-spectacular :
    # ``config.schema`` l'expose avec ses propres droits (siège seulement).
    "SERVE_INCLUDE_SCHEMA": False,
    # Les composants de requête et de réponse divergent (champs en lecture
    # seule, fichiers en écriture seule) : un seul composant mentirait dans
    # un sens ou dans l'autre. Les composants de requête portent le suffixe
    # ``Request``, ceux d'un ``PATCH`` le préfixe ``Patched``.
    "COMPONENT_SPLIT_REQUEST": True,
    # Plusieurs champs ``status`` ou ``kind`` n'ont pas les mêmes valeurs :
    # sans nom explicite, drf-spectacular en fabriquerait un par collision,
    # au nom instable.
    "ENUM_NAME_OVERRIDES": {
        "WorkflowStatusEnum": "expenses.workflow.Status",
        "ProofStatusEnum": "expenses.models.Proof.ProofStatus",
        "ProofKindEnum": "expenses.models.Proof.Kind",
        "BeneficiaryKindEnum": "expenses.models.Beneficiary.Kind",
        "PaymentMethodEnum": "expenses.models.Expense.PaymentMethod",
        "NotificationKindEnum": "notifications.models.Notification.Kind",
        "NotificationLevelEnum": "notifications.models.Notification.Level",
        "ReallocationStatusEnum": "budget.models.BudgetReallocation.Status",
        "OverrunPolicyEnum": "budget.models.OverrunPolicy",
        "ProjectStatusEnum": "core.models.Project.STATUS_CHOICES",
        "ChangeLogActionEnum": "core.models.ChangeLog.Actions",
        "ChangeLogModelEnum": "core.models.ChangeLog.Models",
        "AuditActionEnum": "expenses.models.AuditLog.Action",
        "RoleEnum": "accounts.models.Role",
        "TransitionEnum": "expenses.serializers.TRANSITION_CHOICES",
        "BudgetScopeEnum": "budget.serializers.SCOPE_CHOICES",
    },
    # Voir config/schema.py : en réponse, tout champ est présent.
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.hooks.postprocess_schema_enums",
        "config.schema.reponses_completes",
    ],
    # Ordre stable des opérations et de leurs paramètres : la CI compare le
    # document généré au fichier versionné.
    "SORT_OPERATIONS": True,
    "SORT_OPERATION_PARAMETERS": True,
    # Interface Swagger sans dépendance embarquée : chargée depuis un CDN,
    # elle n'existe qu'en mode debug (config/schema.py).
    "SWAGGER_UI_DIST": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5",
    "SWAGGER_UI_FAVICON_HREF": "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/favicon-32x32.png",
    "SWAGGER_UI_SETTINGS": {"persistAuthorization": True, "displayRequestDuration": True},
}

# Double authentification (TOTP). Le mécanisme est toujours disponible :
# tout titulaire peut enrôler son application, et un compte enrôlé fournit
# son code à chaque connexion. L'obligation, elle, est une politique :
# DJANGO_TOTP_REQUIRED=1 ferme la plateforme aux comptes non enrôlés
# (cf. accounts.middleware). Par défaut, elle n'est pas exigée.
TOTP_REQUIRED = os.environ.get("DJANGO_TOTP_REQUIRED", "0") == "1"
# Nom affiché par l'application d'authentification à côté du compte.
TOTP_ISSUER = "JUSTI INNOV"

# Domaines de messagerie admis pour les comptes (cf. accounts.validators).
# Plusieurs valeurs séparées par des virgules ; comparés en minuscules.
ALLOWED_EMAIL_DOMAINS = [
    d.strip().lower()
    for d in os.environ.get("ALLOWED_EMAIL_DOMAINS", "innovpharma.net").split(",")
    if d.strip()
]
if not ALLOWED_EMAIL_DOMAINS:
    raise ImproperlyConfigured("ALLOWED_EMAIL_DOMAINS ne doit pas être vide.")

# ---------------------------------------------------------------------------
# CORS - frontend Vite
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = [
    o for o in os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:5173").split(",") if o
]
CORS_ALLOW_CREDENTIALS = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Localisation
# ---------------------------------------------------------------------------
# Sans ces réglages, Django appliquerait ses défauts (America/Chicago, en-us) :
# les horodatages d'audit et l'admin s'afficheraient dans un fuseau sans
# rapport avec les pays gérés. Les dates sont stockées en UTC ; chaque pays
# porte son propre fuseau dans `Country.timezone` pour l'affichage local.
LANGUAGE_CODE = "fr"
# Plateforme bilingue : le français est la langue de référence des messages,
# l'anglais vient d'un catalogue unique, ``locale/en`` à la racine du projet
# (décision 42) : une seule commande ``makemessages`` le régénère, une seule
# étape le compile, et la CI refuse une chaîne restée vide. La langue d'une
# réponse suit l'en-tête ``Accept-Language`` envoyé par l'interface.
LANGUAGES = [("fr", "Français"), ("en", "English")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = os.environ.get("DJANGO_TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Stockage des pièces justificatives
# ---------------------------------------------------------------------------
# Object storage compatible S3 (MinIO) dès qu'un point d'accès est configuré ;
# repli sur le disque local sinon, pour permettre les tests et un démarrage
# sans dépendance externe.
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

AWS_S3_ENDPOINT_URL = os.environ.get("AWS_S3_ENDPOINT_URL", "")

if AWS_S3_ENDPOINT_URL:
    _default_storage = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "endpoint_url": AWS_S3_ENDPOINT_URL,
            "access_key": os.environ.get("AWS_ACCESS_KEY_ID", ""),
            "secret_key": os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
            "bucket_name": os.environ.get("AWS_STORAGE_BUCKET_NAME", "justificatifs"),
            # Le contenu n'est jamais public : il est servi par une vue
            # authentifiée qui vérifie le périmètre de l'utilisateur.
            "default_acl": None,
            "querystring_auth": True,
            "signature_version": "s3v4",
            "file_overwrite": False,
            # Au-delà de cette taille, un fichier lu depuis le stockage passe
            # par le disque plutôt que par la mémoire du worker.
            "max_memory_size": 2 * 1024 * 1024,
        },
    }
else:
    _default_storage = {"BACKEND": "django.core.files.storage.FileSystemStorage"}

STORAGES = {
    "default": _default_storage,
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

# Taille maximale d'une pièce justificative (octets).
MAX_PROOF_SIZE = int(os.environ.get("MAX_PROOF_SIZE", 20 * 1024 * 1024))

# Formats acceptés (§5.4). Une liste blanche évite qu'un exécutable ou une page
# HTML active se retrouve stockée et rediffusée comme « justificatif ».
ALLOWED_PROOF_EXTENSIONS = [
    ".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic",
    ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt",
]

# ---------------------------------------------------------------------------
# Alertes et notifications (§8)
# ---------------------------------------------------------------------------
# Seuils de consommation déclenchant une alerte, en pourcentage.
ALERT_THRESHOLDS = [
    int(value)
    for value in os.environ.get("ALERT_THRESHOLDS", "80,90,100").split(",")
    if value.strip()
]

# Une dépense est signalée « inhabituelle » au-delà de ce multiple de la
# moyenne des dépenses validées de son pays.
UNUSUAL_EXPENSE_FACTOR = float(os.environ.get("UNUSUAL_EXPENSE_FACTOR", "5"))

# Valeurs reprises par la configuration métier (WorkflowConfiguration) lors
# de son amorçage par migration ; ensuite, la base fait foi.
UNJUSTIFIED_ALERT_DAYS = int(os.environ.get("UNJUSTIFIED_ALERT_DAYS", "0"))
WARN_WITHOUT_PROOF_SUBMISSION = os.environ.get(
    "WARN_WITHOUT_PROOF_SUBMISSION", "1"
) == "1"



def choisir_email_backend(email_host, *, debug, console):
    """Transport des e-mails, ou refus de démarrer.

    Un serveur SMTP dès qu'il est nommé. Sinon, la console — les messages
    vont dans les journaux — mais seulement en développement ou sur demande
    explicite (``EMAIL_BACKEND_CONSOLE=1``) : en production, un ``EMAIL_HOST``
    oublié ferait disparaître les alertes budgétaires dans les logs sans
    que personne ne s'en aperçoive. Fonction pure, pour être testable sans
    recharger les réglages.
    """
    if email_host:
        return "django.core.mail.backends.smtp.EmailBackend"
    if debug or console:
        return "django.core.mail.backends.console.EmailBackend"
    raise ImproperlyConfigured(
        "EMAIL_HOST est obligatoire hors mode debug : sans lui, aucune alerte "
        "ne part. Pour écrire les messages dans les journaux à la place, "
        "posez explicitement EMAIL_BACKEND_CONSOLE=1."
    )


EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_BACKEND_CONSOLE = os.environ.get("EMAIL_BACKEND_CONSOLE", "0") == "1"
# Un serveur SMTP injoignable ne doit pas bloquer une requête ou une tâche
# planifiée indéfiniment.
EMAIL_TIMEOUT = 10
EMAIL_BACKEND = choisir_email_backend(
    EMAIL_HOST, debug=DEBUG, console=EMAIL_BACKEND_CONSOLE
)
if EMAIL_HOST:
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "1") == "1"

DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", "controle-budgetaire@justi-innov.local"
)
# Adresse publique de l'application, pour les liens dans les e-mails.
APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:5173")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 10},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Durcissement HTTP (actif hors mode debug)
# ---------------------------------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
# Le contrôle de santé de Docker interroge le conteneur en clair, sur sa
# boucle locale, sans passer par le mandataire TLS : redirigé en 301 vers
# https, il ne verrait jamais un 200, le conteneur resterait « unhealthy » et
# le déploiement n'aboutirait jamais. Déclaré sans condition pour que le test
# vérifie la liste réellement appliquée.
# Le contrôle de santé et la collecte Prometheus arrivent en HTTP depuis le
# réseau interne : les rediriger vers HTTPS les rendrait injoignables.
SECURE_REDIRECT_EXEMPT = [r"^api/health/$", r"^metrics$"]

if not DEBUG:
    SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "1") == "1"
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Derrière Caddy, qui termine TLS et émet déjà HSTS pour tout le domaine,
    # Django n'a rien à ajouter : DJANGO_HSTS_SECONDS=0 (deploy/.env.example).
    # La valeur par défaut protège un déploiement où Django serait exposé seul.
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
    # Le préchargement n'est pas un réglage anodin : inscrite sur la liste des
    # navigateurs, la plateforme devient inaccessible en clair, sous-domaines
    # compris, et l'inscription ne se retire pas rapidement. Il est donc
    # activable par l'environnement, et actif par défaut : le back-office et
    # les justificatifs n'ont aucune raison de transiter en clair.
    SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0 and os.environ.get("DJANGO_HSTS_PRELOAD", "1") == "1"

# ---------------------------------------------------------------------------
# Supervision (§ tableau de bord Grafana)
# ---------------------------------------------------------------------------
# Une pile déploie ou non Prometheus et Grafana (deploy/) : l'interface ne
# propose « Supervision » que là où le tableau de bord existe. Le drapeau est
# exposé par ``/api/me/`` et ``/api/configuration/`` ; absent (CI,
# développement), il vaut faux.
SUPERVISION = os.environ.get("SUPERVISION", "0") == "1"
# Jeton présenté par le collecteur Prometheus sur ``/metrics``. Vide : le
# point de collecte n'est pas exposé.
METRICS_TOKEN = os.environ.get("METRICS_TOKEN", "")
# Répertoire partagé des compteurs quand gunicorn fait tourner plusieurs
# workers : chaque processus a sinon ses propres compteurs, et ``/metrics``
# ne montre que ceux du worker qui répond. ``prometheus_client`` et
# ``django_prometheus`` basculent d'eux-mêmes en mode multi-processus dès
# que la variable d'environnement existe — au chargement, d'où l'obligation
# de la poser avant le démarrage et non ici. Elle est lue pour créer le
# répertoire s'il manque ; ``gunicorn.conf.py`` retire les fichiers d'un
# worker mort.
PROMETHEUS_MULTIPROC_DIR = os.environ.get("PROMETHEUS_MULTIPROC_DIR", "")
if PROMETHEUS_MULTIPROC_DIR:
    Path(PROMETHEUS_MULTIPROC_DIR).mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Réglages de test
# ---------------------------------------------------------------------------
# Actifs quand la suite tourne (``manage.py test``, ou ``DJANGO_TEST=1`` pour
# un lanceur qui ne passe pas par ``manage.py``), jamais en service. Ils
# échangent de la fidélité contre de la vitesse là où la couverture n'y perd
# rien :
# - le cache passe en mémoire : le cache partagé n'a de sens qu'entre les
#   workers gunicorn ; en test, chaque compteur de débit et chaque lecture de
#   la configuration du circuit coûtait une requête, et ``--parallel`` aurait
#   exigé une table ``django_cache`` par base clonée. Ce cache n'est plus
#   annulé avec la transaction du test : ``core.tests.runner`` le vide avant
#   chaque test ;
# - les mots de passe sont hachés en MD5 : PBKDF2, avec ses centaines de
#   milliers d'itérations, rendait la création de chaque compte de test plus
#   longue que le test lui-même. Aucun test ne porte sur l'algorithme.
import sys  # noqa: E402 — réservé à ce bloc

EN_TEST = os.environ.get("DJANGO_TEST") == "1" or sys.argv[1:2] == ["test"]
if EN_TEST:
    CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}
    }
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    TEST_RUNNER = "core.tests.runner.LanceurDeTests"
