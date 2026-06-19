# syntax=docker/dockerfile:1.7

FROM python:3.12-slim

ENV PORT=8080

RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

# System deps: TeX Live for PDF generation, poppler for pdf2image
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-fonts-extra \
    lmodern \
    poppler-utils

# UV package manager
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Install dependencies first (Docker layer caching)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .
COPY resume.cls .
COPY frontend/ frontend/
COPY infra/entrypoint.sh /entrypoint.sh

# Install project package into venv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

RUN chmod +x /entrypoint.sh

ENV LATEX_BIN_PATH=/usr/bin \
    PYTHONUNBUFFERED=1

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
