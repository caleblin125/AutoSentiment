# AutoSentiment Backend
FROM python:3.12-slim

WORKDIR /app

# Install system deps for trafilatura (libxml2, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2-dev libxslt-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
