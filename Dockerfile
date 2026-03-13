FROM python:3.12-slim AS base

# System deps (gcc/g++ needed for lxml, scipy wheel builds)
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash curl gcc g++ libxml2-dev libxslt1-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project metadata + source for pip install
COPY pyproject.toml .
COPY src/ src/

# Install all dependencies
RUN pip install --no-cache-dir ".[all]"

# Copy remaining files (scripts, migrations, templates, etc.)
COPY . .

# Make scripts executable
RUN chmod +x scripts/entrypoint.sh

EXPOSE 8000 8501

CMD ["bash", "scripts/entrypoint.sh"]
