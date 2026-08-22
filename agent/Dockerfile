FROM python:3.11-slim

LABEL org.opencontainers.image.title="Phoenix Agent"
LABEL org.opencontainers.image.description="Self-healing agent — observe, detect, diagnose, recover"

# System deps for psycopg2 and Docker SDK
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create __init__.py files for proper Python packages
RUN find /app -type d -name "*.py" -prune -o -type d -print | \
    xargs -I{} touch {}/__init__.py 2>/dev/null || true

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["python", "-m", "agent.main"]
