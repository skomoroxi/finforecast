import pytest


@pytest.fixture(autouse=True)
def _no_second_factor(settings):
    """Tests sign in with force_login; the two-factor tests turn this back on."""
    settings.ADMIN_2FA = False


@pytest.fixture(autouse=True)
def _plain_static_storage(settings):
    """Tests run without collectstatic, so the hashed-manifest storage has no manifest to read."""
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
