"""Settings. Everything environment-specific comes from environment variables (see .env.example)."""

from pathlib import Path

import environ
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CSRF_TRUSTED_ORIGINS=(list, []),
    ADMIN_URL=(str, "admin/"),
    SITE_URL=(str, "http://localhost:8000"),
    INDEXING=(bool, False),
)
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-dev-only")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")
SITE_URL = env("SITE_URL")
# Pre-launch every page is noindex; switched on at launch (TECHNICAL-TASK §10).
INDEXING = env("INDEXING")
# The admin lives on a non-guessable path set per environment.
ADMIN_URL = env("ADMIN_URL")

INSTALLED_APPS = [
    "unfold",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.core",
    "apps.market",
    "apps.forecasts",
    "apps.content",
]

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

ROOT_URLCONF = "finforecast.urls"
WSGI_APPLICATION = "finforecast.wsgi.application"

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
                "apps.core.context_processors.site",
            ],
        },
    },
]

DATABASES = {"default": env.db("DATABASE_URL", default="postgres://finforecast:finforecast@localhost:5432/finforecast")}
DATABASES["default"]["CONN_MAX_AGE"] = 60

REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CACHES = {"default": {"BACKEND": "django_redis.cache.RedisCache", "LOCATION": REDIS_URL}}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = None
CELERY_TASK_IGNORE_RESULT = True
CELERY_TIMEZONE = "UTC"
# One task at a time: the server has little RAM (TECHNICAL-TASK §5.2).
CELERY_WORKER_CONCURRENCY = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = 20
# Data jobs run after midnight UTC, once the previous day is final everywhere (TECHNICAL-TASK §13).
# Order matters: German shares need that day's EUR/USD, so stocks follow fx_metal.
CELERY_BEAT_SCHEDULE = {
    "heartbeat": {"task": "apps.core.tasks.heartbeat", "schedule": crontab(minute="*/5")},
    "update-crypto": {
        "task": "apps.market.tasks.update_group",
        "schedule": crontab(hour=0, minute=15),
        "args": ["crypto"],
    },
    "update-fx-metal": {
        "task": "apps.market.tasks.update_group",
        "schedule": crontab(hour=0, minute=30, day_of_week="tue-sat"),
        "args": ["fx_metal"],
    },
    "update-stocks": {
        "task": "apps.market.tasks.update_group",
        "schedule": crontab(hour=0, minute=50, day_of_week="tue-sat"),
        "args": ["stocks"],
    },
    "update-energy": {
        "task": "apps.market.tasks.update_group",
        "schedule": crontab(hour=3, minute=15, day_of_week="tue-sat"),
        "args": ["energy"],
    },
    # Forecasts cover whatever has a new close, so the second pass picks up energy.
    "forecasts": {"task": "apps.forecasts.tasks.run_due_forecasts", "schedule": crontab(hour=1, minute=30)},
    "forecasts-energy": {"task": "apps.forecasts.tasks.run_due_forecasts", "schedule": crontab(hour=3, minute=45)},
    "adr-ratios": {"task": "apps.market.tasks.recalc_ratios", "schedule": crontab(hour=4, minute=0)},
    "accuracy": {"task": "apps.forecasts.tasks.update_accuracy", "schedule": crontab(hour=4, minute=30)},
    "live-quotes": {
        "task": "apps.market.tasks.refresh_live_quotes",
        "schedule": crontab(minute="*/3", hour="13-21", day_of_week="mon-fri"),
        "options": {"expires": 120},  # skip a turn rather than pile up behind a long job
    },
}

# Market data keys. Never logged; adapters strip them from error messages.
TWELVEDATA_API_KEY = env("TWELVEDATA_API_KEY", default="")
ALPHAVANTAGE_API_KEY = env("ALPHAVANTAGE_API_KEY", default="")
FRED_API_KEY = env("FRED_API_KEY", default="")
FINNHUB_API_KEY = env("FINNHUB_API_KEY", default="")
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("de", "Deutsch")]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Behind Apache (ISPmanager) and later Cloudflare: trust the forwarded host and scheme.
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
    X_FRAME_OPTIONS = "DENY"

UNFOLD = {
    "SITE_TITLE": "FinForecast admin",
    "SITE_HEADER": "FinForecast",
    "SITE_SYMBOL": "monitoring",
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
