FROM python:3.11-slim

LABEL org.opencontainers.image.title="Phoenix Sample App"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["python", "app.py"]
