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
COPY ./containers/elevation/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ./containers/elevation/elevation_container.py .
COPY ./shared_schema.py .

# Create directories and copy services from main pipeline
RUN mkdir -p ./services
COPY ./services/usgs_service.py ./services/

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8004/health || exit 1

# Run the container service
EXPOSE 8004
CMD ["python", "elevation_container.py"]