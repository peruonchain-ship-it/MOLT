FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv
WORKDIR /app
ENV PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv UV_CACHE_DIR=/tmp/uv-cache \
    MOLT_DATA_DIR=/data MOLT_HOST=0.0.0.0 MOLT_PORT=8000
COPY pyproject.toml uv.lock uv.toml ./
RUN uv sync --frozen --no-dev --no-install-project \
    && rm -rf /tmp/uv-cache \
    && groupadd --gid 10001 datalicita \
    && useradd --uid 10001 --gid 10001 --no-create-home datalicita \
    && mkdir /data && chown 10001:10001 /data
COPY molt ./molt
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD /opt/venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3)"
CMD ["/opt/venv/bin/python", "-m", "molt", "serve"]
