FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency management
RUN pip install --no-cache-dir uv

# Copy dependency manifests and install — layer cached unless these files change
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application source
COPY . .

# Railway injects PORT at runtime; default to 8000 for local runs
ENV PORT=8000

# API server — Railway overrides CMD for worker/beat services:
#   worker: celery -A celery_app worker --concurrency=4 -Q default,engine
#   beat:   celery -A celery_app beat --loglevel=info
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port $PORT"]
