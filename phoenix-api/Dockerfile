FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY phoenix-api/requirements.txt /tmp/requirements.txt
COPY agent/requirements.txt /tmp/agent-requirements.txt
COPY requirements-dev.txt /tmp/requirements-dev.txt
RUN sed -i '/^-r /d' /tmp/agent-requirements.txt && \
    pip install --no-cache-dir -r /tmp/requirements.txt \
    -r /tmp/agent-requirements.txt \
    pytest flake8

# Copy the entire project (agent + phoenix-api)
COPY agent /app/agent
COPY phoenix-api /app/phoenix-api
COPY sample-app /app/sample-app
COPY tests /app/tests
COPY pytest.ini .flake8 /app/

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Health check
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Run the API
CMD ["uvicorn", "app.main:app", "--app-dir", "/app/phoenix-api", "--host", "0.0.0.0", "--port", "8000"]
