import pytest


@pytest.fixture(autouse=True)
def _plain_static_storage(settings):
    """Tests run without collectstatic, so the hashed-manifest storage has no manifest to read."""
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
