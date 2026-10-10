# Build from the repository root: docker build --platform linux/amd64 -f backend/Dockerfile -t danger-mark-api:phase6 .
FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/backend MPLCONFIGDIR=/tmp/matplotlib
WORKDIR /app
COPY backend/requirements-phase3-lock.txt /tmp/requirements.txt
RUN pip install --only-binary=:all: --no-cache-dir -r /tmp/requirements.txt && pip check \
    && groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
COPY backend/app /app/backend/app
COPY backend/config /app/backend/config
COPY data/catalog /app/data/catalog
COPY data/processed /app/data/processed
# This is the 2.7 KB pilot subset, never the national population raster.
COPY data/raw/delhi_yamuna/population/worldpop_2023_1km_native.tif /app/data/raw/delhi_yamuna/population/worldpop_2023_1km_native.tif
COPY scripts/requirements-lock.txt /app/scripts/requirements-lock.txt
COPY artifacts/consequences/analysis-1616d67b7b28fb2442d9747f /app/artifacts/consequences/analysis-1616d67b7b28fb2442d9747f
COPY artifacts/evacuation/evacuation-0ef6b5b986d235ed86baed02.json /app/artifacts/evacuation/evacuation-0ef6b5b986d235ed86baed02.json
COPY infra/container_start.py /app/infra/container_start.py
# Data/code stay read-only to the process; only derived caches are writable.
RUN chmod -R a+rX /app && chown -R 10001:10001 /app/artifacts
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"
CMD ["python", "/app/infra/container_start.py"]
