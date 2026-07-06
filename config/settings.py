# =============================================================================
# config/settings.py
# =============================================================================

from pathlib import Path
from decouple import config, Csv

# ── Paths ─────────────────────────────────────────────────────────────────── #

BASE_DIR = Path(__file__).resolve().parent.parent


# ── Security ──────────────────────────────────────────────────────────────── #

SECRET_KEY = config(
    "SECRET_KEY",
    default="django-insecure-change-me-in-production-use-a-long-random-string",
)

DEBUG = config("DEBUG", default=True, cast=bool)

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="*,127.0.0.1,localhost", cast=Csv())


# ── Application definition ────────────────────────────────────────────────── #

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
]

THIRD_PARTY_APPS = [
    "import_export",
]

LOCAL_APPS = [
    "core.apps.CoreConfig",
    "accounts.apps.AccountsConfig",
    "clients.apps.ClientsConfig",
    "formations.apps.FormationsConfig",
    "etudes.apps.EtudesConfig",
    "financial.apps.FinancialConfig",
    "resources.apps.ResourcesConfig",
    "reporting",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

if DEBUG:
    INSTALLED_APPS += ["debug_toolbar"]


# ── Middleware ────────────────────────────────────────────────────────────── #

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

if DEBUG:
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")


# ── URL & WSGI ────────────────────────────────────────────────────────────── #

ROOT_URLCONF = "config.urls"

WSGI_APPLICATION = "config.wsgi.application"


# ── Templates ─────────────────────────────────────────────────────────────── #

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # Inject InstituteInfo into every template
                "core.context_processors.institute_info",
            ],
        },
    },
]


# ── Database ──────────────────────────────────────────────────────────────── #

DATABASES = {
    "default": {
        "ENGINE": config("DB_ENGINE", default="django.db.backends.sqlite3"),
        "NAME": config("DB_NAME", default=str(BASE_DIR / "db.sqlite3")),
        "USER": config("DB_USER", default=""),
        "PASSWORD": config("DB_PASSWORD", default=""),
        "HOST": config("DB_HOST", default=""),
        "PORT": config("DB_PORT", default=""),
    }
}

# Wrap every HTTP request in a transaction — ensures signals fire correctly
# and prevents partial saves on unexpected errors.
DATABASES["default"]["ATOMIC_REQUESTS"] = True


# ── Password validation ───────────────────────────────────────────────────── #

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# ── Internationalisation ──────────────────────────────────────────────────── #

LANGUAGE_CODE = "fr-dz"

TIME_ZONE = "Africa/Algiers"

USE_I18N = True

USE_L10N = True

USE_TZ = True

# Algerian Dinar display formatting used in templates via {{ value|floatformat:2 }}
CURRENCY_SYMBOL = "DA"


# ── Static files ──────────────────────────────────────────────────────────── #

STATIC_URL = "/static/"

STATICFILES_DIRS = [BASE_DIR / "static"]

STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


# ── Media files ───────────────────────────────────────────────────────────── #

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"


# ── Authentication ────────────────────────────────────────────────────────── #

LOGIN_URL = "accounts:login"

LOGIN_REDIRECT_URL = "reporting:dashboard"

LOGOUT_REDIRECT_URL = "accounts:login"

SESSION_COOKIE_AGE = 60 * 60 * 8  # 8 hours — one business day
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"


# ── File uploads ──────────────────────────────────────────────────────────── #

# 10 MB cap on individual uploaded files (receipts, CVs, deliverables)
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ── Business logic constants ──────────────────────────────────────────────── #

# Equipment idle threshold used by Equipment.is_idle and reporting/utils.py
EQUIPMENT_IDLE_THRESHOLD_DAYS = 90


# ── Django import-export ──────────────────────────────────────────────────── #

IMPORT_EXPORT_USE_TRANSACTIONS = True
IMPORT_EXPORT_SKIP_ADMIN_LOG = False


# ── Debug Toolbar ─────────────────────────────────────────────────────────── #

if DEBUG:
    INTERNAL_IPS = ["127.0.0.1"]

    DEBUG_TOOLBAR_CONFIG = {
        "SHOW_TOOLBAR_CALLBACK": lambda request: DEBUG,
        "SHOW_COLLAPSED": True,
    }


# ── Logging ───────────────────────────────────────────────────────────────── #

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {asctime} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": BASE_DIR / "logs" / "isi.log",
            "maxBytes": 5 * 1024 * 1024,  # 5 MB
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console", "file"],
            "level": config("DJANGO_LOG_LEVEL", default="WARNING"),
            "propagate": False,
        },
        "financial": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "formations": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# Ensure logs directory exists
(BASE_DIR / "logs").mkdir(exist_ok=True)
