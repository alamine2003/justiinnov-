"""Configuration Django pour :attr:`config`.

La gestion des pays et organisations (section 5.1) est fournie par
l'application :mod:`core`.
"""

import os
from pathlib import Path

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
    # apps
    "core",
    "accounts",
    "budget",
    "expenses",
    "notifications",
    "reporting",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.CurrentUserMiddleware",
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

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "justi_innov"),
        "USER": os.environ.get("POSTGRES_USER", "justi"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "justi"),
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

# ---------------------------------------------------------------------------
# Authentification REST
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "SEARCH_PARAM": "search",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    # ``login`` protège l'obtention du jeton (cf. core.views.LoginRateThrottle).
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "2000/hour",
        "login": "10/min",
    },
}

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
LANGUAGE_CODE = "fr-fr"
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

EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
if EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "1") == "1"
else:
    # Sans serveur SMTP configuré, les messages sont écrits dans les logs
    # plutôt que perdus silencieusement.
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

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

if not DEBUG:
    SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "1") == "1"
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True