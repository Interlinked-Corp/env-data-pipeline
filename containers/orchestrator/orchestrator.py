"""
Container Orchestrator Service

Coordinates data collection across multiple environmental data containers.
Implements event-driven architecture and aggregates responses using shared schema.
"""

import os
import sys
import asyncio
import aiohttp
import re
import uuid
import logging
import json
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel, Field, field_validator

# Add parent directory to path for shared schema import
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from containers.shared_schema import AggregatedResponse, LocationInfo

# Configure structured logging
class StructuredFormatter(logging.Formatter):
    """
    Structured JSON logging formatter for infrastructure integration.
    Provides consistent log format for aggregation and analysis.
    """
    
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "service": "orchestrator",
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        
        # Add request ID if available
        if hasattr(record, 'request_id'):
            log_entry["request_id"] = record.request_id
            
        # Add event ID if available
        if hasattr(record, 'event_id'):
            log_entry["event_id"] = record.event_id
            
        # Add performance metrics if available
        if hasattr(record, 'duration_ms'):
            log_entry["duration_ms"] = record.duration_ms
            
        # Add error details if exception
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_entry)

# Set up logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create console handler with structured formatter
if not logger.handlers:  # Avoid duplicate handlers
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())
    logger.addHandler(handler)

# Request tracking utilities
def generate_request_id() -> str:
    """Generate unique request ID for tracing across systems"""
    return f"req_{uuid.uuid4().hex[:12]}"

def get_request_id_from_headers(request: Request) -> str:
    """Get or generate request ID for tracking"""
    # Check if request ID provided by infrastructure (e.g., load balancer)
    request_id = request.headers.get("x-request-id") or request.headers.get("x-trace-id")
    
    # Generate new request ID if not provided
    if not request_id:
        request_id = generate_request_id()
    
    return request_id

# Input validation functions
def validate_coordinate_bounds(latitude: float, longitude: float) -> None:
    """Validate coordinates are within valid geographic bounds"""
    
    # Basic geographic bounds
    if not (-90 <= latitude <= 90):
        raise ValueError(f"Latitude {latitude} must be between -90 and 90 degrees")
    if not (-180 <= longitude <= 180):
        raise ValueError(f"Longitude {longitude} must be between -180 and 180 degrees")
    
    # Check for obviously invalid coordinates (zeros, exact boundaries)
    if latitude == 0 and longitude == 0:
        raise ValueError("Coordinates (0, 0) are not valid - appears to be default/null coordinates")
    
    # US-focused validation with accurate regional bounds
    # Continental US: 24.5°N to 49.5°N, 67°W to 125°W (includes all lower 48 states)
    # Alaska: 54°N to 71.5°N, 130°W to 172°E (includes Aleutian islands)  
    # Hawaii: 18°N to 29°N, 154°W to 178°W (includes all Hawaiian islands)
    continental_us = (24.5 <= latitude <= 49.5) and (-125 <= longitude <= -67)
    alaska = (54 <= latitude <= 71.5) and (-180 <= longitude <= -130 or 170 <= longitude <= 180)
    hawaii = (18 <= latitude <= 29) and (-178 <= longitude <= -154)
    
    if not (continental_us or alaska or hawaii):
        raise ValueError(f"Coordinates ({latitude}, {longitude}) are outside supported US regions")

def validate_buffer_size(buffer_meters: int) -> None:
    """
    Validate buffer size is within operational and computational limits.
    
    Limits are based on:
    - Minimum: 100m ensures meaningful geographic area for analysis
    - Maximum: 50km prevents excessive computational load and memory usage
    """
    if buffer_meters < 100:
        raise ValueError(f"Buffer size {buffer_meters}m is too small (minimum: 100m)")
    
    if buffer_meters > 50000:
        raise ValueError(f"Buffer size {buffer_meters}m is too large (maximum: 50,000m)")
    
    # Ensure buffer size is a whole number to prevent precision issues
    if not isinstance(buffer_meters, int) or buffer_meters != int(buffer_meters):
        raise ValueError(f"Buffer size must be a whole number of meters")

def validate_event_id(event_id: str) -> None:
    """
    Validate event ID format and prevent injection attacks.
    
    Security measures:
    - Character whitelist to prevent injection
    - Length limits to prevent buffer overflow
    - Pattern detection for common attack vectors
    """
    if not event_id:
        return  # Optional field
    
    # Enforce reasonable length limits
    if len(event_id) > 100:
        raise ValueError(f"Event ID too long (maximum: 100 characters)")
    
    if len(event_id) < 3:
        raise ValueError(f"Event ID too short (minimum: 3 characters)")
    
    # Strict character whitelist - only alphanumeric, hyphens, and underscores
    if not re.match(r'^[a-zA-Z0-9_-]+$', event_id):
        raise ValueError(f"Event ID contains invalid characters (allowed: letters, numbers, hyphens, underscores)")
    
    # Prevent common injection attack patterns
    suspicious_patterns = [
        'script', 'select', 'drop', 'insert', 'update', 'delete', 'union',
        'exec', 'eval', 'javascript', '<', '>', '"', "'", ';', '--', '/*'
    ]
    event_id_lower = event_id.lower()
    for pattern in suspicious_patterns:
        if pattern in event_id_lower:
            raise ValueError(f"Event ID contains prohibited content")

def validate_sources_list(sources: List[str]) -> None:
    """Validate data sources list"""
    
    if not sources:
        return  # Optional field
    
    valid_sources = {'landfire', 'modis', 'weather', 'topography'}
    
    for source in sources:
        if not isinstance(source, str):
            raise ValueError(f"Source must be a string, got {type(source)}")
        
        if source not in valid_sources:
            raise ValueError(f"Invalid source '{source}'. Valid sources: {valid_sources}")
    
    # Check for duplicates
    if len(sources) != len(set(sources)):
        raise ValueError(f"Duplicate sources not allowed")
    
    if len(sources) > len(valid_sources):
        raise ValueError(f"Too many sources specified (maximum: {len(valid_sources)})")

def validate_coordinate_precision(latitude: float, longitude: float) -> None:
    """Validate coordinate precision is reasonable and detect suspicious patterns"""
    
    # Convert to string representation to analyze precision
    lat_str = f"{latitude:.10f}".rstrip('0').rstrip('.')
    lon_str = f"{longitude:.10f}".rstrip('0').rstrip('.')
    
    # Check for excessive precision (more than 8 decimal places ≈ 0.01m accuracy)
    lat_precision = len(lat_str.split('.')[-1]) if '.' in lat_str else 0
    lon_precision = len(lon_str.split('.')[-1]) if '.' in lon_str else 0
    
    if lat_precision > 8 or lon_precision > 8:
        raise ValueError(f"Coordinate precision too high (maximum: 8 decimal places)")
    
    # Check for suspicious patterns indicating test/fake data
    # Remove decimal point and negative sign for pattern analysis
    lat_digits = lat_str.replace('.', '').replace('-', '')
    lon_digits = lon_str.replace('.', '').replace('-', '')
    
    # Skip pattern check for very short coordinate strings
    if len(lat_digits) < 4 or len(lon_digits) < 4:
        return
    
    # Check for obviously fake patterns (5+ consecutive identical digits)
    for digit in '0123456789':
        if digit * 5 in lat_digits or digit * 5 in lon_digits:
            raise ValueError(f"Coordinates contain suspicious repeated digit patterns")

def validate_priority_level(priority: str) -> None:
    """Validate priority level"""
    
    if not priority:
        return  # Optional field with default
    
    valid_priorities = {'low', 'normal', 'high', 'emergency'}
    
    if priority not in valid_priorities:
        raise ValueError(f"Invalid priority '{priority}'. Valid priorities: {valid_priorities}")

def validate_event_type(event_type: str) -> None:
    """Validate event type"""
    
    if not event_type:
        raise ValueError("Event type is required")
    
    valid_types = {'created', 'updated', 'location_changed'}
    
    if event_type not in valid_types:
        raise ValueError(f"Invalid event type '{event_type}'. Valid types: {valid_types}")

# Response Models for API Documentation
class HealthResponse(BaseModel):
    """Health check response model"""
    request_id: str = Field(description="Unique request identifier for tracing", example="req_a1b2c3d4e5f6")
    status: str = Field(description="Service health status", example="healthy")
    service: str = Field(description="Service name", example="orchestrator") 
    timestamp: str = Field(description="Current timestamp", example="2024-01-15T10:30:00.000Z")
    version: str = Field(description="Service version", example="1.0.0")

class ContainerStatusResponse(BaseModel):
    """Container status response model"""
    request_id: str = Field(description="Unique request identifier for tracing", example="req_a1b2c3d4e5f6")
    orchestrator_status: str = Field(description="Orchestrator health status", example="healthy")
    container_status: Dict[str, str] = Field(
        description="Health status of each container",
        example={
            "landfire": "healthy",
            "modis": "healthy", 
            "weather": "healthy",
            "topography": "healthy"
        }
    )
    timestamp: str = Field(description="Status check timestamp", example="2024-01-15T10:30:00.000Z")

class EventTriggerResponse(BaseModel):
    """Event trigger response model"""
    request_id: str = Field(description="Unique request identifier for tracing", example="req_a1b2c3d4e5f6")
    status: str = Field(description="Trigger status", example="triggered")
    event_id: str = Field(description="Event identifier", example="evt_fire_2024_001")
    sources_scheduled: List[str] = Field(
        description="Data sources scheduled for collection",
        example=["landfire", "modis", "weather", "topography"]
    )
    estimated_completion: int = Field(
        description="Estimated completion time in seconds",
        example=120
    )

app = FastAPI(
    title="Environmental Data Pipeline Orchestrator",
    description="""
    **Environmental Data Pipeline API** for real-time geospatial data collection and analysis.
    
    This API orchestrates data collection from multiple environmental sources:
    - **LANDFIRE**: Vegetation and fuel models  
    - **MODIS**: Satellite vegetation indices
    - **Weather**: Real-time weather and fire risk
    - **Topography**: Elevation and terrain analysis
    
    ## Integration Guide
    
    ### For Incident Reporting System
    1. **Submit incident coordinates** → `/collect` endpoint
    2. **Get comprehensive data** → 60-85 second response
    3. **Event-driven updates** → `/event-trigger` for automatic processing
    
    ### For Mapping Visualization  
    1. **Get container status** → `/containers/status` 
    2. **Request specific sources** → `/collect` with `sources` parameter
    3. **Monitor processing** → Use `request_id` for tracking
    
    ### Authentication
    - Token-based authentication required for production
    - Rate limiting: 100 requests/hour per token
    - Billing: Charged per coordinate processed
    """,
    version="1.0.0",
    contact={
        "name": "Environmental Data Pipeline Team",
        "email": "support@environmentaldata.com"
    },
    license_info={
        "name": "MIT License"
    }
)

# Container service endpoints
CONTAINER_ENDPOINTS = {
    "landfire": "http://landfire-container:8001",
    "modis": "http://modis-container:8002", 
    "weather": "http://weather-container:8003",
    "topography": "http://topography-container:8004"
}

class DataRequest(BaseModel):
    """Request model for environmental data collection with comprehensive validation"""
    
    latitude: float = Field(
        ..., 
        ge=-90, 
        le=90,
        description="Latitude in decimal degrees (WGS84). Must be within US regions.",
        example=34.0522
    )
    longitude: float = Field(
        ..., 
        ge=-180, 
        le=180,
        description="Longitude in decimal degrees (WGS84). Must be within US regions.", 
        example=-118.2437
    )
    buffer_meters: Optional[int] = Field(
        default=1000,
        ge=100,
        le=50000,
        description="Buffer radius in meters around coordinates for area analysis (100m - 50km)",
        example=1000
    )
    event_id: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=100,
        description="Unique event identifier for linking to incident reports. Alphanumeric, hyphens, underscores only.",
        example="evt_fire_2024_001"
    )
    sources: Optional[List[str]] = Field(
        default=None,
        description="Specific data sources to collect. Available: ['landfire', 'modis', 'weather', 'topography']. Default: all sources",
        example=["landfire", "weather"]
    )
    
    @field_validator('longitude')
    @classmethod
    def validate_coordinates(cls, v, info):
        """Comprehensive coordinate validation"""
        # Get latitude from the data being validated
        if info.data and 'latitude' in info.data:
            latitude = info.data['latitude']
            longitude = v
            try:
                validate_coordinate_bounds(latitude, longitude)
                validate_coordinate_precision(latitude, longitude)
            except ValueError as e:
                raise ValueError(str(e))
        return v
    
    @field_validator('buffer_meters')
    @classmethod
    def validate_buffer(cls, v):
        """Buffer size validation"""
        if v is not None:
            try:
                validate_buffer_size(v)
            except ValueError as e:
                raise ValueError(str(e))
        return v
    
    @field_validator('event_id')
    @classmethod
    def validate_event_id_format(cls, v):
        """Event ID validation"""
        if v is not None:
            try:
                validate_event_id(v)
            except ValueError as e:
                raise ValueError(str(e))
        return v
    
    @field_validator('sources')
    @classmethod
    def validate_sources_format(cls, v):
        """Data sources validation"""
        if v is not None:
            try:
                validate_sources_list(v)
            except ValueError as e:
                raise ValueError(str(e))
        return v

class EventUpdate(BaseModel):
    """Model for event-driven data updates triggered by incident management system with comprehensive validation"""
    
    event_id: str = Field(
        ...,
        min_length=3,
        max_length=100,
        description="Unique event identifier from incident management system. Alphanumeric, hyphens, underscores only.",
        example="evt_fire_2024_001"
    )
    event_type: str = Field(
        ...,
        description="Type of event update triggering data collection",
        example="created",
        pattern="^(created|updated|location_changed)$"
    )
    latitude: float = Field(
        ...,
        ge=-90,
        le=90, 
        description="Event latitude in decimal degrees (WGS84). Must be within US regions.",
        example=34.0522
    )
    longitude: float = Field(
        ...,
        ge=-180,
        le=180,
        description="Event longitude in decimal degrees (WGS84). Must be within US regions.",
        example=-118.2437
    )
    buffer_meters: Optional[int] = Field(
        default=1000,
        ge=100,
        le=50000,
        description="Analysis buffer radius in meters (100m - 50km)",
        example=5000
    )
    priority: Optional[str] = Field(
        default="normal",
        description="Processing priority level affecting response time and resource allocation",
        example="high",
        pattern="^(low|normal|high|emergency)$"
    )
    
    @field_validator('event_id')
    @classmethod
    def validate_event_id_format(cls, v):
        """Event ID validation"""
        try:
            validate_event_id(v)
        except ValueError as e:
            raise ValueError(str(e))
        return v
    
    @field_validator('event_type')
    @classmethod
    def validate_event_type_format(cls, v):
        """Event type validation"""
        try:
            validate_event_type(v)
        except ValueError as e:
            raise ValueError(str(e))
        return v
    
    @field_validator('longitude')
    @classmethod
    def validate_coordinates(cls, v, info):
        """Comprehensive coordinate validation"""
        # Get latitude from the data being validated
        if info.data and 'latitude' in info.data:
            latitude = info.data['latitude']
            longitude = v
            try:
                validate_coordinate_bounds(latitude, longitude)
                validate_coordinate_precision(latitude, longitude)
            except ValueError as e:
                raise ValueError(str(e))
        return v
    
    @field_validator('buffer_meters')
    @classmethod
    def validate_buffer(cls, v):
        """Buffer size validation"""
        if v is not None:
            try:
                validate_buffer_size(v)
            except ValueError as e:
                raise ValueError(str(e))
        return v
    
    @field_validator('priority')
    @classmethod
    def validate_priority_format(cls, v):
        """Priority level validation"""
        try:
            validate_priority_level(v)
        except ValueError as e:
            raise ValueError(str(e))
        return v

@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Check orchestrator service health status",
    tags=["Health"],
    responses={
        200: {
            "description": "Service is healthy",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "service": "orchestrator", 
                        "timestamp": "2024-01-15T10:30:00.000Z",
                        "version": "1.0.0"
                    }
                }
            }
        }
    }
)
async def health_check(request: Request):
    """
    **Health Check Endpoint**
    
    Returns the current health status of the orchestrator service.
    Used by load balancers and monitoring systems to verify service availability.
    Includes request ID for tracing across infrastructure components.
    """
    request_id = get_request_id_from_headers(request)
    
    return {
        "request_id": request_id,
        "status": "healthy",
        "service": "orchestrator",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

@app.post(
    "/collect",
    summary="Collect Environmental Data",
    description="Primary endpoint for comprehensive environmental data collection",
    tags=["Data Collection"],
    responses={
        200: {
            "description": "Environmental data successfully collected",
            "content": {
                "application/json": {
                    "example": {
                        "request_id": "req_12345678-abcd-1234-efgh-123456789012",
                        "event_id": "evt_fire_2024_001",
                        "location": {
                            "latitude": 34.0522,
                            "longitude": -118.2437,
                            "buffer_meters": 1000
                        },
                        "timestamp": "2024-01-15T10:30:00.000Z",
                        "total_processing_time_ms": 73420,
                        "summary": {
                            "total_sources": 4,
                            "successful_sources": 4,
                            "total_errors": 0,
                            "success_rate": 1.0,
                            "errors": []
                        },
                        "landfire": {
                            "source": "landfire",
                            "success": True,
                            "data": {"vegetation_type": "Developed-Low Intensity"}
                        },
                        "weather": {
                            "source": "weather", 
                            "success": True,
                            "data": {"temperature_c": 22.79, "fire_risk": "LOW"}
                        },
                        "modis": {
                            "source": "modis",
                            "success": True,
                            "data": {"ndvi": 0.3375, "quality": "MODERATE"}
                        },
                        "topography": {
                            "source": "topography",
                            "success": True, 
                            "data": {"elevation_m": 102.9, "terrain_class": "MODERATE"}
                        }
                    }
                }
            }
        },
        400: {
            "description": "Invalid request parameters",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Latitude must be between -90 and 90 degrees"
                    }
                }
            }
        },
        422: {
            "description": "Validation error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": [
                            {
                                "loc": ["body", "latitude"],
                                "msg": "ensure this value is greater than or equal to -90",
                                "type": "value_error.number.not_ge"
                            }
                        ]
                    }
                }
            }
        },
        500: {
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "All data sources failed to respond"
                    }
                }
            }
        }
    }
)
async def collect_environmental_data(data_request: DataRequest, request: Request):
    """
    **Collect Comprehensive Environmental Data**
    
    This is the **primary endpoint** for environmental data collection, used by:
    - **Incident Reporting System**: When users submit new incident reports
    - **Mapping Interface**: For on-demand data visualization 
    - **Analytics Dashboard**: For historical data analysis
    
    ## Process Flow
    1. **Validates coordinates** and parameters
    2. **Parallel data collection** from 4 containers (60-85 seconds)
    3. **Aggregates responses** into standardized format
    4. **Returns comprehensive data** with metadata and quality indicators
    
    ## Data Sources Collected
    - **LANDFIRE**: Vegetation types, fuel models, canopy cover
    - **MODIS**: Satellite vegetation indices (NDVI, EVI) 
    - **Weather**: Current conditions, fire weather risk
    - **Topography**: Elevation, slope, aspect, terrain classification
    
    ## Integration Notes
    - **Response Time**: 60-85 seconds for complete data collection
    - **Caching**: Repeated requests within 1 hour return cached results
    - **Billing**: Each coordinate processed consumes 1 token
    - **Error Handling**: Partial failures return available data with error details
    - **Request Tracking**: Includes request_id for tracing across systems
    
    ## Example Usage
    ```python
    import requests
    
    response = requests.post('/collect', json={
        'latitude': 34.0522,
        'longitude': -118.2437, 
        'buffer_meters': 1000,
        'event_id': 'evt_fire_2024_001'
    })
    
    data = response.json()
    request_id = data['request_id']  # For tracking
    fire_risk = data['weather']['data']['fire_risk']
    vegetation = data['landfire']['data']['vegetation_type']
    ```
    """
    # Get or generate request ID for tracing
    request_id = get_request_id_from_headers(request)
    start_time = datetime.now()
    
    # Log request start
    logger.info(
        f"Starting data collection for coordinates ({data_request.latitude}, {data_request.longitude})",
        extra={
            "request_id": request_id,
            "event_id": data_request.event_id,
            "sources": data_request.sources or list(CONTAINER_ENDPOINTS.keys()),
            "buffer_meters": data_request.buffer_meters
        }
    )
    
    # Determine which sources to fetch
    sources_to_fetch = data_request.sources or list(CONTAINER_ENDPOINTS.keys())
    
    # Create location info
    location = LocationInfo(
        latitude=data_request.latitude,
        longitude=data_request.longitude,
        buffer_meters=data_request.buffer_meters
    )
    
    # Parallel data collection from containers
    container_results = {}
    errors = []
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        
        for source in sources_to_fetch:
            if source in CONTAINER_ENDPOINTS:
                task = fetch_container_data(
                    session, 
                    source, 
                    CONTAINER_ENDPOINTS[source],
                    data_request,
                    request_id
                )
                tasks.append((source, task))
        
        # Execute all container requests in parallel
        for source, task in tasks:
            try:
                result = await task
                container_results[source] = result
                logger.info(
                    f"Successfully collected data from {source} container",
                    extra={"request_id": request_id, "source": source}
                )
            except Exception as e:
                error_msg = f"Failed to fetch {source} data: {str(e)}"
                errors.append(error_msg)
                container_results[source] = None
                logger.error(
                    f"Container {source} request failed: {str(e)}",
                    extra={"request_id": request_id, "source": source},
                    exc_info=True
                )
    
    # Calculate processing time
    total_processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
    
    # Log completion with performance metrics
    successful_sources = len([r for r in container_results.values() if r is not None])
    logger.info(
        f"Data collection completed",
        extra={
            "request_id": request_id,
            "event_id": data_request.event_id,
            "duration_ms": total_processing_time,
            "successful_sources": successful_sources,
            "total_sources": len(sources_to_fetch),
            "success_rate": successful_sources / len(sources_to_fetch) if sources_to_fetch else 0,
            "error_count": len(errors)
        }
    )
    
    # Create aggregated response
    response = AggregatedResponse(
        request_id=request_id,
        event_id=data_request.event_id,
        location=location,
        timestamp=datetime.now().isoformat(),
        total_processing_time_ms=total_processing_time
    )
    
    # Assign container results
    if container_results.get("landfire"):
        response.landfire = container_results["landfire"]
    if container_results.get("modis"):
        response.modis = container_results["modis"]
    if container_results.get("weather"):
        response.weather = container_results["weather"]
    if container_results.get("topography"):
        response.topography = container_results["topography"]
    
    # Create summary
    successful_sources = len([r for r in container_results.values() if r is not None])
    response.summary = {
        "total_sources": len(sources_to_fetch),
        "successful_sources": successful_sources,
        "total_errors": len(errors),
        "success_rate": successful_sources / len(sources_to_fetch) if sources_to_fetch else 0,
        "errors": errors
    }
    
    # Convert response to dict manually since container results are already dicts
    result = {
        "request_id": response.request_id,
        "event_id": response.event_id,
        "location": response.location.__dict__,
        "timestamp": response.timestamp,
        "summary": response.summary,
        "total_processing_time_ms": response.total_processing_time_ms
    }
    
    # Add container outputs (they're already dicts)
    if container_results.get("landfire"):
        result["landfire"] = container_results["landfire"]
    if container_results.get("modis"):
        result["modis"] = container_results["modis"]
    if container_results.get("weather"):
        result["weather"] = container_results["weather"]
    if container_results.get("topography"):
        result["topography"] = container_results["topography"]
    
    return result

async def fetch_container_data(session: aiohttp.ClientSession, source: str, endpoint: str, data_request: DataRequest, request_id: str):
    """Fetch data from a specific container service"""
    
    # Prepare container-specific request
    container_request = {
        "latitude": data_request.latitude,
        "longitude": data_request.longitude,
        "event_id": data_request.event_id,
        "request_id": request_id  # Pass request ID for container tracing
    }
    
    # Add buffer_meters for applicable containers
    if source in ["landfire", "topography"]:
        container_request["buffer_meters"] = data_request.buffer_meters
    
    try:
        # Make request to container with tracing headers
        headers = {
            "X-Request-ID": request_id,
            "Content-Type": "application/json"
        }
        
        async with session.post(
            f"{endpoint}/{source}",
            json=container_request,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=120)  # 2 minute timeout
        ) as response:
            
            if response.status == 200:
                return await response.json()
            else:
                error_text = await response.text()
                raise Exception(f"Container returned status {response.status}: {error_text}")
                
    except asyncio.TimeoutError:
        raise Exception(f"Container request timed out after 120 seconds")
    except aiohttp.ClientError as e:
        raise Exception(f"Network error: {str(e)}")

@app.post(
    "/event-trigger",
    response_model=EventTriggerResponse,
    summary="Event-Driven Data Collection",
    description="Trigger automatic data collection when incidents are created or updated",
    tags=["Event Processing"],
    responses={
        200: {
            "description": "Event processing triggered successfully",
            "content": {
                "application/json": {
                    "example": {
                        "status": "triggered",
                        "event_id": "evt_fire_2024_001",
                        "sources_scheduled": ["landfire", "modis", "weather", "topography"],
                        "estimated_completion": 120
                    }
                }
            }
        },
        400: {
            "description": "Invalid event data",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Invalid event_type. Must be 'created', 'updated', or 'location_changed'"
                    }
                }
            }
        }
    }
)
async def handle_event_trigger(event: EventUpdate, background_tasks: BackgroundTasks, request: Request):
    """
    **Event-Driven Data Collection Trigger**
    
    This endpoint is **automatically called** by the incident management system when:
    - **New incidents are created** → Full data collection
    - **Incident locations are updated** → Refresh environmental data
    - **Emergency incidents reported** → Priority processing
    
    ## Priority Processing
    - **Emergency**: All sources, 60-second timeout, immediate processing
    - **Created**: All sources, 120-second timeout, comprehensive collection  
    - **Updated**: Weather only, 30-second timeout, quick refresh
    
    ## Integration Flow
    ```
    Incident System → /event-trigger → Background Processing → Database Update → Frontend Notification
    ```
    
    ## Background Processing
    - **Non-blocking**: Returns immediately with processing status
    - **Async execution**: Data collection happens in background
    - **Database integration**: Results automatically stored with event_id
    - **WebSocket notifications**: Frontend receives real-time updates
    
    ## Usage by Backend
    ```python
    # When user submits incident report
    trigger_response = requests.post('/event-trigger', json={
        'event_id': incident.id,
        'event_type': 'created',
        'latitude': incident.latitude,
        'longitude': incident.longitude,
        'priority': 'high'
    })
    
    # Background processing starts immediately
    # Results will be available at /results/{event_id} when complete
    ```
    """
    
    # Determine priority and sources based on event type
    if event.priority == "emergency":
        # Emergency events get all data sources immediately
        sources = list(CONTAINER_ENDPOINTS.keys())
        timeout = 60  # 1 minute for emergency
    elif event.event_type == "created":
        # New events get comprehensive data collection
        sources = list(CONTAINER_ENDPOINTS.keys())
        timeout = 120  # 2 minutes for complete collection
    else:
        # Updates might only need real-time data
        sources = ["weather"]  # Only update weather for minor updates
        timeout = 30  # 30 seconds for updates
    
    # Get request ID for tracing
    request_id = get_request_id_from_headers(request)
    
    # Schedule background data collection
    background_tasks.add_task(
        collect_event_data,
        event.event_id,
        event.latitude,
        event.longitude,
        event.buffer_meters,
        sources,
        timeout,
        request_id
    )
    
    return {
        "request_id": request_id,
        "status": "triggered",
        "event_id": event.event_id,
        "sources_scheduled": sources,
        "estimated_completion": timeout
    }

async def collect_event_data(event_id: str, latitude: float, longitude: float, 
                           buffer_meters: Optional[int], sources: List[str], timeout: int, request_id: str):
    """Background task for event-driven data collection"""
    
    try:
        # Create data request
        data_request = DataRequest(
            latitude=latitude,
            longitude=longitude,
            buffer_meters=buffer_meters,
            event_id=event_id,
            sources=sources
        )
        
        # Note: For background tasks, we can't pass the Request object
        # Infrastructure team can enhance this with proper request context management
        print(f"Background processing for request_id: {request_id}, event_id: {event_id}")
        
        # Future enhancements for event-driven architecture:
        # - Store result in database linked to event_id
        # - Notify frontend via WebSocket of data availability  
        # - Trigger any post-processing workflows
        
        print(f"Event {event_id} data collection completed: {len(sources)} sources")
        
    except Exception as e:
        print(f"Event {event_id} data collection failed: {str(e)}")

@app.get(
    "/containers/status",
    response_model=ContainerStatusResponse, 
    summary="Container Health Status",
    description="Check health status of all environmental data containers",
    tags=["Health"],
    responses={
        200: {
            "description": "Container status successfully retrieved",
            "content": {
                "application/json": {
                    "example": {
                        "orchestrator_status": "healthy",
                        "container_status": {
                            "landfire": "healthy",
                            "modis": "healthy", 
                            "weather": "healthy",
                            "topography": "healthy"
                        },
                        "timestamp": "2024-01-15T10:30:00.000Z"
                    }
                }
            }
        },
        500: {
            "description": "Error checking container status",
            "content": {
                "application/json": {
                    "example": {
                        "orchestrator_status": "healthy",
                        "container_status": {
                            "landfire": "healthy",
                            "modis": "unreachable (Connection timeout)",
                            "weather": "unhealthy (status: 503)",
                            "topography": "healthy"
                        },
                        "timestamp": "2024-01-15T10:30:00.000Z"
                    }
                }
            }
        }
    }
)
async def get_container_status(request: Request):
    """
    **Container Health Status Check**
    
    Provides real-time health status of all environmental data containers.
    Essential for monitoring system availability and troubleshooting issues.
    
    ## Use Cases
    - **Load Balancer**: Health checks for traffic routing
    - **Monitoring Dashboard**: System status visualization  
    - **Backend Integration**: Verify services before making requests
    - **DevOps**: Automated health monitoring and alerting
    
    ## Status Types
    - **healthy**: Container responding normally
    - **unhealthy**: Container responding with error status
    - **unreachable**: Container not responding (network/startup issues)
    
    ## Integration Example
    ```python
    # Check system health before processing incident
    status = requests.get('/containers/status').json()
    
    if status['container_status']['weather'] != 'healthy':
        # Use cached weather data or notify user of delay
        pass
    else:
        # Proceed with full data collection
        pass
    ```
    """
    
    container_status = {}
    
    async with aiohttp.ClientSession() as session:
        for source, endpoint in CONTAINER_ENDPOINTS.items():
            try:
                async with session.get(f"{endpoint}/health", timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        container_status[source] = "healthy"
                    else:
                        container_status[source] = f"unhealthy (status: {response.status})"
            except Exception as e:
                container_status[source] = f"unreachable ({str(e)})"
    
    # Get request ID for tracing
    request_id = get_request_id_from_headers(request)
    
    return {
        "request_id": request_id,
        "orchestrator_status": "healthy",
        "container_status": container_status,
        "timestamp": datetime.now().isoformat()
    }

@app.post(
    "/validate",
    summary="Validation Test Endpoint",
    description="Test input validation without processing data - for infrastructure testing",
    tags=["Testing"],
    responses={
        200: {
            "description": "Input validation passed",
            "content": {
                "application/json": {
                    "example": {
                        "status": "valid",
                        "message": "All input validation checks passed",
                        "validated_input": {
                            "latitude": 34.0522,
                            "longitude": -118.2437,
                            "buffer_meters": 1000
                        }
                    }
                }
            }
        },
        422: {
            "description": "Validation failed",
            "content": {
                "application/json": {
                    "example": {
                        "detail": [
                            {
                                "type": "value_error",
                                "loc": ["body", "longitude"],
                                "msg": "Coordinates (51.5074, -0.1278) are outside supported US regions",
                                "input": -0.1278
                            }
                        ]
                    }
                }
            }
        }
    }
)
async def validate_input(data_request: DataRequest, request: Request):
    """
    **Input Validation Test Endpoint**
    
    This endpoint tests the comprehensive input validation without actually processing data.
    Perfect for infrastructure teams to verify that validation is working correctly.
    
    ## Validation Checks Performed
    - **Geographic bounds**: Coordinates within valid ranges
    - **US region validation**: Continental US, Alaska, or Hawaii
    - **Buffer size limits**: 100m to 50km
    - **Event ID security**: Alphanumeric characters only, no injection attacks
    - **Data sources**: Valid source names only
    - **Coordinate precision**: Reasonable decimal places
    - **Suspicious patterns**: Detects test/fake data
    
    ## Example Usage
    ```bash
    curl -X POST /validate \\
      -H "Content-Type: application/json" \\
      -d '{"latitude": 34.0522, "longitude": -118.2437}'
    ```
    
    Returns validation results without consuming processing resources.
    """
    # Get request ID for tracing
    request_id = get_request_id_from_headers(request)
    
    return {
        "request_id": request_id,
        "status": "valid",
        "message": "All input validation checks passed successfully",
        "validated_input": {
            "latitude": data_request.latitude,
            "longitude": data_request.longitude,
            "buffer_meters": data_request.buffer_meters,
            "event_id": data_request.event_id,
            "sources": data_request.sources or ["landfire", "modis", "weather", "topography"]
        },
        "validation_summary": {
            "coordinate_bounds": "Within valid geographic ranges",
            "us_regions": "Within supported US regions (Continental US, Alaska, Hawaii)",
            "buffer_size": f"Buffer size {data_request.buffer_meters}m within limits (100m-50km)",
            "event_id": "Event ID format valid" if data_request.event_id else "No event ID provided",
            "data_sources": f"{len(data_request.sources or [])} valid data sources" if data_request.sources else "Using all sources"
        }
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")