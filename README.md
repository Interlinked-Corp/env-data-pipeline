# Environmental Data Pipeline

Containerized microservices for retrieving geospatial environmental data. Provides vegetation, weather, topography, and satellite data via REST APIs.

## Overview

**Architecture**: 4 containerized services with event coordination  
**Input**: Latitude/longitude coordinates via REST API  
**Output**: Standardized environmental data (JSON + binary GeoTIFF)  
**Coverage**: Continental United States

### Services

| Service | Port | Data Source | Purpose |
|---------|------|-------------|---------|
| Orchestrator | 8000 | All sources | API gateway, coordination |
| LANDFIRE | 8001 | USFS | Vegetation, fuel models |
| MODIS | 8002 | NASA | Satellite vegetation indices |
| Weather | 8003 | OpenWeatherMap | Current weather, forecasts |
| Topography | 8004 | USGS 3DEP | High-resolution elevation |

## Quick Start

### Deploy
```bash
docker-compose up --build
```

### Test
```bash
# Health check
curl http://localhost:8000/health

# Data request (Los Angeles)
curl -X POST "http://localhost:8000/collect" \
  -H "Content-Type: application/json" \
  -d '{"latitude": 34.0522, "longitude": -118.2437}'
```

### Individual containers
```bash
curl -X POST "http://localhost:8001/landfire" \
  -d '{"latitude": 34.0522, "longitude": -118.2437}'
```

## API Usage

### Python
```python
import requests

response = requests.post("http://localhost:8000/collect", json={
    "latitude": 34.0522,
    "longitude": -118.2437,
    "buffer_meters": 1000,
    "event_id": "request_001"
})

data = response.json()
print(f"Vegetation: {data['landfire']['interpreted_data']['coordinate_specific']['vegetation_type']}")
print(f"Temperature: {data['weather']['interpreted_data']['coordinate_specific']['temperature_celsius']}°C")
```

### Response Format
```json
{
  "request_id": "req_abc123",
  "event_id": "request_001",
  "location": {"latitude": 34.0522, "longitude": -118.2437},
  "summary": {"total_sources": 4, "successful_sources": 4},
  "landfire": {
    "source": "LANDFIRE",
    "interpreted_data": {
      "coordinate_specific": {
        "vegetation_type": "Developed-Medium Intensity",
        "fire_risk_vegetation": "LOW"
      }
    },
    "raw_data": {"vegetation_type": {"data": "base64_geotiff", "size_bytes": 131476}}
  },
  "weather": { /* weather data */ },
  "modis": { /* satellite data */ },
  "topography": { /* elevation data */ }
}
```

## Data Sources

### LANDFIRE
- **Products**: Vegetation type, fuel models, canopy cover/height
- **Resolution**: 30m spatial resolution
- **Update**: Annual (2-3 year lag)

### MODIS (NASA)
- **Products**: NDVI/EVI vegetation indices, land surface temperature
- **Resolution**: 250m-1km
- **Update**: 8-16 day composites

### OpenWeatherMap
- **Products**: Current weather, 5-day forecast, fire weather risk
- **Resolution**: Point interpolation
- **Update**: Real-time

### USGS 3DEP
- **Products**: Digital elevation models, slope, aspect
- **Resolution**: 10m spatial resolution
- **Update**: Multi-year cycles

## Development

### Setup
```bash
git clone <repository-url>
cd env-data-pipeline

# Configure environment
cp .env.example .env
# Edit .env with API keys:
# OPENWEATHER_API_KEY=your_key
# AWS_ACCESS_KEY_ID=your_key (for LANDFIRE metadata)
# AWS_SECRET_ACCESS_KEY=your_secret

# Start services
docker-compose up --build

# Run tests
python tests/test_pipeline.py
```

### Environment Variables
```bash
# Required
OPENWEATHER_API_KEY=<api-key>
AWS_ACCESS_KEY_ID=<access-key>
AWS_SECRET_ACCESS_KEY=<secret-key>

# Optional
AWS_DEFAULT_REGION=us-west-2
ENVIRONMENT=development
LOG_LEVEL=INFO
```

## Production Deployment

### Resource Requirements
| Service | CPU | Memory | Replicas |
|---------|-----|--------|----------|
| Orchestrator | 1 vCPU | 2GB | 2-3 |
| LANDFIRE | 2 vCPU | 4GB | 1-2 |
| MODIS | 1 vCPU | 2GB | 1-2 |
| Weather | 0.5 vCPU | 1GB | 1-2 |
| Topography | 1 vCPU | 2GB | 1-2 |

### Health Monitoring
- **Endpoints**: `/health` (simple), `/status` (detailed)
- **Logging**: Structured JSON with request/event ID tracking
- **Timeout**: 10s health checks

### External Dependencies
| Service | Endpoint | Rate Limits |
|---------|----------|-------------|
| OpenWeatherMap | api.openweathermap.org | 1,000/day |
| USGS | elevation.nationalmap.gov | None |
| NASA ORNL | modis.ornl.gov | None |
| AWS S3 | s3.amazonaws.com | AWS limits |

## Status

### Complete
- Microservice architecture (4 containers)
- Standardized data schemas
- Event ID coordination
- Health checks and monitoring
- Request ID tracking
- Structured logging
- Integration tests

### Production TODO
- Kubernetes manifests
- API authentication
- Rate limiting
- Container registry
- Monitoring (Prometheus/Grafana)
- Auto-scaling
- CORS configuration

## Performance

- **Response Time**: 30-60 seconds
- **Concurrent Users**: 50-100
- **Peak Load**: 500 requests/hour
- **Availability**: 99.5% target

## Contributing

```bash
# Create branch
git checkout -b feature/name

# Test changes
python tests/test_pipeline.py
docker-compose up --build

# Commit
git commit -m "feat: description"
```

### Standards
- PEP 8 style
- Type hints required
- Error handling for all external APIs
- Container schema compliance

### Test Coordinates
- Los Angeles: `34.0522, -118.2437`
- Yellowstone: `44.6, -110.5`
- Death Valley: `36.5, -117.0`

---

**Version**: 1.0.0  
**Requirements**: Docker 20.10+, 8GB RAM