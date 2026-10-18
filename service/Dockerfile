# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
COPY requirements.txt requirements.lock ./
# Optional build-only CA bundle for a corporate TLS-inspecting proxy. It is never
# copied into the image, and TLS verification remains enabled in both paths.
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then \
      pip install --cert /run/secrets/build_ca --no-cache-dir -r requirements.txt; \
    else pip install --no-cache-dir -r requirements.txt; fi \
    && useradd --uid 10001 --create-home processor
COPY --chown=processor:processor . .
USER processor
EXPOSE 8080
# A synchronous worker is killed before the Cloud Run / Tasks request deadlines.
# No background execution survives a returned HTTP response.
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 1 --worker-class sync --timeout 1500 --graceful-timeout 15 --access-logfile - --error-logfile - app:app"]
