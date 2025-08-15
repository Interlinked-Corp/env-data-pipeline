FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for GIS processing
RUN apt-get update && apt-get install -y \
    curl \
    gdal-bin \
    libgdal-dev \
    && rm -rf /var/lib/apt/lists/*

# Set GDAL environment variables
ENV GDAL_DATA=/usr/share/gdal
ENV PROJ_LIB=/usr/share/proj

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY landfire_container.py .
COPY shared_schema.py .

# Copy services from main pipeline
COPY services/landfire_service.py ./services/
COPY metadata/landfire_interpretation.py ./metadata/

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Run the container service
EXPOSE 8001
CMD ["python", "landfire_container.py"]