# One image for web, worker and beat.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# Static files are collected at build time and served by WhiteNoise.
RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput \
    && useradd --system --uid 1000 --home /app app \
    && chown -R app:app /app
USER app

ARG GIT_SHA=dev
ENV GIT_SHA=${GIT_SHA}

EXPOSE 8000
CMD ["gunicorn", "finforecast.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2", "--max-requests", "1000", "--max-requests-jitter", "100", "--access-logfile", "-"]
