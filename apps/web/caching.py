"""Finished pages are kept in Redis, compressed, until the data or the text changes."""

import time
import zlib
from functools import wraps

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse

VERSION_KEY = "web:version"
PAGE_SECONDS = 6 * 3600
BROWSER_SECONDS = 300
EDGE_SECONDS = 3600


def version() -> int:
    current = cache.get(VERSION_KEY)
    if current is None:
        current = int(time.time())
        cache.set(VERSION_KEY, current, None)
    return current


def bump() -> None:
    """Every cached page is out of date from now on. Old entries age out of Redis by themselves."""
    cache.set(VERSION_KEY, int(time.time() * 1000), None)


def cached_page(view):
    """Cache a public HTML page for everyone. Only for views that do not depend on the visitor."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.method != "GET" or request.GET:
            return view(request, *args, **kwargs)
        key = f"web:page:{version()}:{request.path}"
        stored = cache.get(key)
        if stored is not None:
            response = HttpResponse(zlib.decompress(stored))
        else:
            response = view(request, *args, **kwargs)
            if hasattr(response, "render") and callable(response.render):
                response.render()
            if response.status_code != 200:
                return response
            cache.set(key, zlib.compress(response.content, 6), PAGE_SECONDS)
        if not settings.DEBUG:
            response["Cache-Control"] = f"public, max-age={BROWSER_SECONDS}, s-maxage={EDGE_SECONDS}"
        return response

    return wrapper
