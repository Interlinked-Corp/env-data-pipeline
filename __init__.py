"""
Environmental Data Pipeline

Containerized microservices for retrieving environmental data by latitude and longitude coordinates.
Integrates LANDFIRE, MODIS, USGS, and weather data sources through REST APIs.
"""

__version__ = "2.0.0"
__author__ = "Interlinked Corp"

# Orchestrator endpoints for environmental data services
# All container access is routed through the orchestrator

# Development endpoints (localhost)
ORCHESTRATOR_ENDPOINT_DEV = 'http://localhost:8000'
DATA_COLLECTION_ENDPOINT_DEV = f'{ORCHESTRATOR_ENDPOINT_DEV}/collect'
CONTAINER_STATUS_ENDPOINT_DEV = f'{ORCHESTRATOR_ENDPOINT_DEV}/containers/status'

# Production endpoints (backend integration)
ORCHESTRATOR_ENDPOINT_PROD = 'http://container-orchestrator:8000'
DATA_COLLECTION_ENDPOINT_PROD = f'{ORCHESTRATOR_ENDPOINT_PROD}/collect'
CONTAINER_STATUS_ENDPOINT_PROD = f'{ORCHESTRATOR_ENDPOINT_PROD}/containers/status'

# Default to development endpoints
ORCHESTRATOR_ENDPOINT = ORCHESTRATOR_ENDPOINT_DEV
DATA_COLLECTION_ENDPOINT = DATA_COLLECTION_ENDPOINT_DEV
CONTAINER_STATUS_ENDPOINT = CONTAINER_STATUS_ENDPOINT_DEV

# Import shared schema for external use
try:
    from containers.shared_schema import validate_coordinates, validate_buffer_size
    __all__ = ["ORCHESTRATOR_ENDPOINT", "DATA_COLLECTION_ENDPOINT", "CONTAINER_STATUS_ENDPOINT",
              "ORCHESTRATOR_ENDPOINT_DEV", "DATA_COLLECTION_ENDPOINT_DEV", "CONTAINER_STATUS_ENDPOINT_DEV", 
              "ORCHESTRATOR_ENDPOINT_PROD", "DATA_COLLECTION_ENDPOINT_PROD", "CONTAINER_STATUS_ENDPOINT_PROD",
              "validate_coordinates", "validate_buffer_size"]
except ImportError:
    __all__ = ["ORCHESTRATOR_ENDPOINT", "DATA_COLLECTION_ENDPOINT", "CONTAINER_STATUS_ENDPOINT",
              "ORCHESTRATOR_ENDPOINT_DEV", "DATA_COLLECTION_ENDPOINT_DEV", "CONTAINER_STATUS_ENDPOINT_DEV", 
              "ORCHESTRATOR_ENDPOINT_PROD", "DATA_COLLECTION_ENDPOINT_PROD", "CONTAINER_STATUS_ENDPOINT_PROD"]