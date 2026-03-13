FROM python:3.12-slim AS base

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy all application code
COPY . .

# Install all dependencies (including ui and dev extras)
RUN pip install --no-cache-dir ".[all]"

# Make scripts executable
RUN chmod +x scripts/entrypoint.sh

EXPOSE 8000 8501

CMD ["bash", "scripts/entrypoint.sh"]
