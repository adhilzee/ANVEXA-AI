# Base python image
FROM python:3.11-slim

# Prevents Python from writing pyc files and buffers stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8000 \
    ANVEXA_ENVIRONMENT=production \
    ANVEXA_DATABASE_URL=sqlite:///./anvexa_demo.db \
    ANVEXA_JWT_SECRET_KEY=anvexa-super-secret-key-production-change-in-prod-32bytes! \
    ANVEXA_DOCUMENT_STORAGE_PATH=./storage/documents

WORKDIR /app

# Install minimal system utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy application source
COPY . /app

# Create storage directory
RUN mkdir -p /app/storage/documents

# Seed demonstration data so the app has verified sample paper out-of-the-box
RUN python -m scripts.seed_demo

EXPOSE 8000

# Start server
CMD ["python", "run_demo.py"]
