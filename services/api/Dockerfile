# syntax=docker/dockerfile:1.7

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates curl git \
    && rm -rf /var/lib/apt/lists/*

COPY services/agent-runtime /app/services/agent-runtime
COPY services/api /app/services/api

RUN ln -s /app/services/agent-runtime /agent-runtime

RUN python -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org --upgrade pip \
    && python -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -e /app/services/agent-runtime \
    && python -m pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org -e /app/services/api

WORKDIR /app/services/api

EXPOSE 8000

CMD ["bash", "-lc", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
