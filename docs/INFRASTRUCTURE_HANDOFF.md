# Environmental Data Pipeline - Infrastructure Handoff Document

## Overview
This document outlines the production deployment requirements for the Environmental Data Pipeline, a containerized microservices application that collects and processes environmental data from multiple sources (LANDFIRE, MODIS, Weather, Elevation).

## Application Architecture

### Core Services
- **Orchestrator**: Main API gateway and coordinator (Port 8000)
- **LANDFIRE Service**: Vegetation and fuel data (Port 8001)
- **MODIS Service**: Satellite vegetation indices (Port 8002) 
- **Weather Service**: Current weather and forecasts (Port 8003)
- **Elevation Service**: USGS DEM data (Port 8004)

### Infrastructure Services
- **Redis**: Caching layer (Port 6379)
- **RabbitMQ**: Message queue (Port 5672, Management UI 15672)

### Container Images
All services are built from Python 3.11-slim base images with specific dependencies for GIS processing.

## Resource Requirements

### Compute Resources
| Service | CPU | Memory | Storage | Replicas |
|---------|-----|--------|---------|----------|
| Orchestrator | 1 vCPU | 2GB RAM | 1GB | 2-3 |
| LANDFIRE | 2 vCPU | 4GB RAM | 2GB | 1-2 |
| MODIS | 1 vCPU | 2GB RAM | 1GB | 1-2 |
| Weather | 0.5 vCPU | 1GB RAM | 512MB | 1-2 |
| Elevation | 1 vCPU | 2GB RAM | 1GB | 1-2 |
| Redis | 0.5 vCPU | 1GB RAM | 5GB | 1 |
| RabbitMQ | 0.5 vCPU | 1GB RAM | 2GB | 1 |

### Network Requirements
- **Ingress**: HTTPS only (443), HTTP redirect (80)
- **Internal**: Services communicate on private network
- **Egress**: HTTPS to external APIs (OpenWeatherMap, USGS, NASA)

## Environment Configuration

### Required Environment Variables

#### Production Secrets (Secure Storage Required)
```bash
# OpenWeatherMap API
OPENWEATHER_API_KEY=<secret-key>

# AWS Credentials (for LANDFIRE S3 access)
AWS_ACCESS_KEY_ID=<access-key>
AWS_SECRET_ACCESS_KEY=<secret-key>
AWS_DEFAULT_REGION=us-west-2

# RabbitMQ (if not using managed service)
RABBITMQ_DEFAULT_USER=pipeline
RABBITMQ_DEFAULT_PASS=<secure-password>
```

#### Service Configuration
```bash
# Environment
ENVIRONMENT=production
OPENWEATHER_ENV=production

# Redis Connection
REDIS_URL=redis://redis-service:6379

# RabbitMQ Connection  
RABBITMQ_URL=amqp://user:pass@rabbitmq-service:5672

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### Environment-Specific Configs
- **Development**: localhost endpoints, verbose logging
- **Staging**: staging APIs, debug logging enabled
- **Production**: production APIs, structured logging only

## Networking & Security

### External API Dependencies
| Service | Endpoint | Purpose | Rate Limits |
|---------|----------|---------|-------------|
| OpenWeatherMap | api.openweathermap.org | Weather data | 1000 calls/day |
| USGS | elevation.nationalmap.gov | Elevation data | No limit |
| NASA ORNL | modis.ornl.gov | MODIS satellite | No limit |
| AWS S3 | s3.us-west-2.amazonaws.com | LANDFIRE data | AWS limits |

### CORS Configuration
```bash
# Allow frontend domains
CORS_ORIGINS=https://app.yourdomain.com,https://staging-app.yourdomain.com

# For local development
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
```

### Security Requirements
- **TLS**: All external traffic must use HTTPS
- **API Authentication**: Implement API key authentication
- **Container Security**: Run as non-root user (UID 1000)
- **Network Isolation**: Services on private network
- **Secrets Management**: Use cloud-native secret stores

## API Endpoints

### Public Endpoints
```
POST /collect
- Purpose: Main data collection endpoint
- Input: {"latitude": float, "longitude": float, "buffer_meters": int}
- Output: Aggregated environmental data
- Expected Load: 100-500 requests/hour
- Response Time: 30-60 seconds (external API dependent)

GET /containers/status  
- Purpose: Service health monitoring
- Output: Health status of all containers
- Expected Load: Monitoring system polls every 30s

GET /health
- Purpose: Load balancer health check
- Output: Simple healthy/unhealthy status
- Expected Load: Load balancer polls every 10s
```

### Health Checks
All services expose `/health` endpoints for container orchestration:
- **Healthy**: Returns 200 with service status
- **Unhealthy**: Returns 503 if dependencies unavailable
- **Timeout**: 10 second timeout for health checks

## Data Persistence

### Stateful Services
- **Redis**: Requires persistent volume (5GB) for caching
- **RabbitMQ**: Requires persistent volume (2GB) for queue durability

### Backup Requirements
- **Redis**: Daily snapshots recommended
- **RabbitMQ**: Queue definitions backup recommended
- **Application**: Stateless, no backup required

### Data Format
- **Input**: JSON coordinates and parameters
- **Output**: JSON with base64-encoded binary GeoTIFF data
- **No file storage**: All data returned in API responses

## Monitoring & Observability

### Health Monitoring
```bash
# Container health checks (implemented)
curl http://service:port/health

# Service dependency checks
curl http://orchestrator:8000/containers/status
```

### Metrics (To Be Implemented)
- **Application**: Request count, response times, error rates
- **Infrastructure**: CPU, memory, disk usage
- **Business**: Successful data retrievals per source

### Logging Requirements
- **Format**: Structured JSON logs
- **Level**: INFO for production, DEBUG for staging
- **Retention**: 30 days minimum
- **Aggregation**: Centralized logging system recommended

### Alerting Needs
- **Service Down**: Any container health check fails
- **High Error Rate**: >5% of requests fail
- **Slow Response**: >2 minutes average response time
- **External API Failures**: Weather/satellite services unavailable

## Deployment Specifications

### Container Registry
- **Images**: All services containerized with Docker
- **Base**: Python 3.11-slim with GIS dependencies
- **Security**: Vulnerability scanning required
- **Tagging**: Use semantic versioning (v1.0.0)

### Orchestration Requirements
- **Kubernetes** (preferred) or **AWS ECS**
- **Rolling updates** for zero-downtime deployments
- **Resource limits** enforced per service
- **Service discovery** for internal communication

### Load Balancing
- **External**: Application Load Balancer with SSL termination
- **Internal**: Service mesh or cluster load balancing
- **Session**: Stateless application, no session affinity needed

## Scaling Strategy

### Horizontal Scaling
- **Orchestrator**: Scale 2-5 instances based on request volume
- **Data Services**: Scale 1-3 instances per service
- **Infrastructure**: Redis single instance, RabbitMQ cluster if needed

### Auto-scaling Triggers
- **CPU**: Scale up at 70% CPU utilization
- **Memory**: Scale up at 80% memory utilization  
- **Response Time**: Scale up if average >90 seconds

### Performance Expectations
- **Concurrent Users**: 50-100 simultaneous requests
- **Peak Load**: 500 requests/hour
- **Response Time**: 30-60 seconds per request
- **Availability**: 99.5% uptime target

## Development Support

### Local Development
- **Docker Compose**: Provided for local testing
- **Hot Reload**: Supported for development
- **Test Data**: Sample coordinates and expected outputs provided

### CI/CD Integration Points
- **Build**: `docker build` from repository root
- **Test**: Health check endpoints and integration tests
- **Deploy**: Rolling update strategy recommended

## Disaster Recovery

### Backup Strategy
- **Code**: Git repository (primary source)
- **Configuration**: Environment variables and secrets
- **Data**: Redis snapshots, RabbitMQ definitions

### Recovery Process
- **RTO**: 2 hours maximum
- **RPO**: 24 hours (acceptable data loss)
- **Failover**: Multi-AZ deployment recommended

## Contact Information

### Application Team
- **Primary Contact**: [Your Name/Team]
- **Repository**: [Git Repository URL]
- **Documentation**: See README.md and PRODUCTION_READINESS.md

### Escalation
- **P1 Issues**: Application team + Infrastructure team
- **P2-P3 Issues**: Infrastructure team first contact
- **Business Hours**: [Your timezone and hours]

## Appendix

### Sample Request/Response
```bash
# Request
curl -X POST https://api.yourdomain.com/v1/collect \
  -H "Content-Type: application/json" \
  -d '{"latitude": 34.0522, "longitude": -118.2437}'

# Response (truncated)
{
  "request_id": "uuid",
  "location": {"latitude": 34.0522, "longitude": -118.2437},
  "summary": {"total_sources": 4, "successful_sources": 4},
  "landfire": {"raw_data": "base64-encoded-geotiff..."},
  "modis": {"raw_data": "satellite-data..."},
  "weather": {"raw_data": "weather-data..."},
  "elevation": {"raw_data": "elevation-data..."}
}
```

### Dependencies Versions
- **Python**: 3.11
- **FastAPI**: 0.104.1
- **Redis**: 7-alpine
- **RabbitMQ**: 3-management-alpine
- **Rasterio**: 1.3.9 (GIS processing)
- **GDAL**: Latest (geospatial libraries)

---

**Document Version**: 1.0  
**Last Updated**: [Current Date]  
**Next Review**: [Date + 3 months]