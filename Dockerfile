# Use official lightweight Python image
FROM python:3.11-slim

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBIAN_FRONTEND=noninteractive \
    DATA_DIR=/app/data \
    PORT=8000

WORKDIR /app

# Install basic tools and font packages for WhatsApp Web rendering
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    fonts-liberation \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies list and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium and all OS-level shared libraries required by Playwright
RUN playwright install --with-deps chromium

# Copy the rest of the application
COPY . .

# Ensure data directory exists
RUN mkdir -p /app/data/sessions

# Expose default port
EXPOSE 8000

# Run FastAPI app with dynamic port assigned by Railway
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
