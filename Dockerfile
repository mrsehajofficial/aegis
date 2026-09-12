FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy dependency definition
COPY pyproject.toml .

# Install dependencies using uv
RUN uv pip install --system --no-cache -e .

# Copy project files
COPY . .

# Run database migrations and start bot
CMD ["sh", "-c", "alembic upgrade head && python -m app.main"]
