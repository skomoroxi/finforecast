from django.conf import settings


def site(request):
    return {"SITE_URL": settings.SITE_URL, "INDEXING": settings.INDEXING}
