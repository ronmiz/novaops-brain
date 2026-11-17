# One image, three entry points (Lesson 14): the MCP tool server, the agent API, the renewal worker.
# Build:  docker build -t novaops-brain:$(git rev-parse --short HEAD) .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONUTF8=1 \
    NOVAOPS_DATASET_DIR=/data/dataset NOVAOPS_DB_PATH=/data/var/novaops.db

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY novaops/ novaops/
COPY server/ server/

# Non-root: the process can write only its own state volume.
RUN useradd --create-home --uid 10001 novaops && mkdir -p /data/var && chown -R novaops /data
USER novaops

EXPOSE 8000 9880
CMD ["uvicorn", "novaops.api:app", "--host", "0.0.0.0", "--port", "8000"]
