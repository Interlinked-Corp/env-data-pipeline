FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY ./containers/modis/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ./containers/modis/modis_container.py .
COPY ./containers/shared_schema.py ./containers/

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

# Run the container service
EXPOSE 8002
CMD ["python", "modis_container.py"]