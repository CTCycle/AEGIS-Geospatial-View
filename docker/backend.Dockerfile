FROM python:3.14.0-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.8.7 /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
COPY AEGIS ./AEGIS

RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["/opt/venv/bin/python", "-m", "uvicorn", "AEGIS.server.app:app", "--host", "0.0.0.0", "--port", "8000"]
