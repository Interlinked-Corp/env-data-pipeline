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
  -d '{"latitude": 34.0522, "longitude": -118.2437, "buffer_meters": 1000}'
```

### Individual containers
```bash
curl -X POST "http://localhost:8001/landfire" \
  -H "Content-Type: application/json" \
  -d '{"latitude": 34.0522, "longitude": -118.2437, "buffer_meters": 1000}'
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
print(f"Vegetation: {data['landfire']['interpreted_data']['coordinate_specific']['vegetation_class']}")
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
        "vegetation_class": "Developed-Roads",
        "vegetation_pixel_value": 7299,
        "fuel_model_class": "Non-burnable",
        "canopy_cover_percent": 0
      }
    },
    "raw_data": {"vegetation_type": {"data": "base64_geotiff", "size_bytes": 131476}}
  },
  "weather": {
    "source": "OpenWeatherMap",
    "interpreted_data": {
      "coordinate_specific": {
        "temperature_celsius": 21.13,
        "humidity_percent": 82,
        "fire_weather_risk": "LOW",
        "weather_description": "clear sky"
      }
    }
  },
  "modis": {
    "source": "MODIS_ORNL",
    "interpreted_data": {
      "coordinate_specific": {
        "ndvi_latest": 0.218,
        "evi_latest": null,
        "vegetation_health": "STRESSED",
        "fire_risk_vegetation": "HIGH",
        "last_observation_date": "2025-06-26",
        "land_surface_temperature_c": 33.65
      }
    }
  },
  "topography": {
    "source": "USGS_3DEP", 
    "interpreted_data": {
      "coordinate_specific": {
        "elevation_m": 0.0,
        "terrain_classification": "LOW",
        "fire_risk_terrain": "LOW"
      }
    }
  }
}
```

## Data Sources

### LANDFIRE
- **Products**: Vegetation types (1,069 classifications), fuel models, canopy cover/height
- **Resolution**: 30m spatial resolution (250m for some products)
- **Update**: Annual (LF24 = 2024 data)
- **S3 Integration**: Real-time CSV metadata lookup for accurate classifications

### MODIS (NASA ORNL)
- **Products**: NDVI/EVI vegetation indices, LAI, FPAR, GPP, land surface temperature
- **Resolution**: 250m spatial resolution
- **Update**: 8-16 day composites
- **Processing Time**: ~52 seconds (largest component)
- **Data Currency**: `last_observation_date` field shows most recent satellite pass
- **Health Assessment**: Automatic vegetation health classification (HEALTHY/MODERATE/STRESSED)

### OpenWeatherMap
- **Products**: Current weather, 5-day forecast, fire weather risk assessment
- **Resolution**: Point interpolation with grid data
- **Update**: Real-time (hourly updates)
- **Processing Time**: ~100ms (fastest service)

### USGS 3DEP
- **Products**: Digital elevation models, slope, aspect, terrain analysis
- **Resolution**: 10-30m spatial resolution
- **Update**: Multi-year cycles
- **Processing Time**: ~260ms

## Development

### Setup
```bash
git clone <repository-url>
cd env-data-pipeline

# Configure environment
cp .env.example .env
# Edit .env with required API key:
# OPENWEATHER_API_KEY=your_key

# Configure AWS credentials (for LANDFIRE S3 metadata)
aws configure

# Start services
docker-compose up --build

# Run tests
python tests/test_pipeline.py
```

### Environment Variables
```bash
# Required
OPENWEATHER_API_KEY=<api-key>

# AWS credentials via mounted ~/.aws directory (set with: aws configure)
# No AWS environment variables needed for development

# Optional
ENVIRONMENT=development
LOG_LEVEL=INFO
RABBITMQ_DEFAULT_USER=pipeline_user
RABBITMQ_DEFAULT_PASS=pipeline_dev_pass
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
- S3 metadata integration (1,069 LANDFIRE classifications)
- Real environmental data processing
- Performance testing and validation

### Production TODO
- API authentication and authorization
- Redis caching integration
- Rate limiting implementation
- Retry logic with exponential backoff
- Input validation enhancement
- Batch coordinate processing
- Container auto-scaling configuration
- Database persistence for request history

## Performance

- **Response Time**: 50-60 seconds (MODIS processing ~52s)
- **Success Rate**: 100% (4/4 data sources operational)
- **Data Consistency**: Perfect (identical pixel values on repeated requests)
- **Geographic Coverage**: Continental United States
- **Current Throughput**: Single request processing (concurrent batching planned)

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
- Los Angeles: `34.0522, -118.2437` (Urban - Developed-Roads)
- Yellowstone: `44.6, -110.5` (Forest - Montane Sagebrush Steppe)
- Death Valley: `36.5, -117.0` (Desert - Creosotebush Desert Scrub)
- Seattle: `47.5086, -122.3551` (Urban - Developed areas)

---

**Version**: 1.0.0  
**Requirements**: Docker 20.10+, 8GB RAM