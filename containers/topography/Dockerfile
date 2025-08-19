FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for GIS processing
RUN apt-get update && apt-get install -y \
    curl \
    gdal-bin \
    libgdal-dev \
    g++ \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set GDAL environment variables
ENV GDAL_DATA=/usr/share/gdal
ENV PROJ_LIB=/usr/share/proj

# Copy requirements
COPY ./containers/topography/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ./containers/topography/topography_container.py .
COPY ./containers/shared_schema.py ./containers/

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8004/health || exit 1

# Run the container service
EXPOSE 8004
CMD ["python", "topography_container.py"]