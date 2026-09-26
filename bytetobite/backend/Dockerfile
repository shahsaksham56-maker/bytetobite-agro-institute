# ═══════════════════════════════════════════════════════════════
# ByteToBite API — production-ready image
# ═══════════════════════════════════════════════════════════════
FROM python:3.11-slim

# ─────────────────────────────────────────────
# ENV
# ─────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ─────────────────────────────────────────────
# WORKDIR
# ─────────────────────────────────────────────
WORKDIR /app

# ─────────────────────────────────────────────
# SYSTEM DEPS (needed for psycopg2 / asyncpg / cryptography)
# ─────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ─────────────────────────────────────────────
# PYTHON DEPS (cached layer — only rebuilds if requirements change)
# ─────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─────────────────────────────────────────────
# APP CODE
# ─────────────────────────────────────────────
COPY . .

# ─────────────────────────────────────────────
# PORTS
# ─────────────────────────────────────────────
EXPOSE 8000

# ─────────────────────────────────────────────
# HEALTHCHECK
# ─────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:${PORT:-8000}/health || exit 1

# ─────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2 --proxy-headers"]