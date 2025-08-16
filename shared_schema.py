"""
Shared Data Schema for Environmental Data Pipeline Containers

This module defines the standardized output format that all containers must conform to.
Each vertical container (LANDFIRE, MODIS, Weather, Elevation, future formats) must
output data in this unified structure to enable seamless integration and API consumption.

Version: 1.0
Created: August 5, 2025
"""

from typing import Dict, List, Optional, Union, Any
from dataclasses import dataclass, field
from datetime import datetime
import json

@dataclass
class LocationInfo:
    """Standardized location information for all data sources"""
    latitude: float
    longitude: float
    buffer_meters: Optional[int] = None
    coordinate_system: str = "EPSG:4326"  # Default to WGS84

@dataclass
class ProcessingMetadata:
    """Standardized processing metadata for all containers"""
    processing_time_ms: int
    data_currency: str  # ISO8601 timestamp of when source data was created
    retrieved_at: str   # ISO8601 timestamp of when data was fetched
    quality_score: float  # 0.0-1.0 quality assessment
    container_id: str
    container_version: str

@dataclass
class VisualizationData:
    """Standardized visualization format for frontend consumption"""
    arrays: List[List[Union[int, float]]]  # 2D arrays for mapping
    legends: Dict[str, Dict[str, Any]]     # Value → display info mapping
    bounds: Dict[str, float]               # Geographic boundaries
    resolution_meters: Optional[float] = None
    color_scheme: Optional[str] = None

@dataclass
class InterpretedData:
    """Standardized interpreted data structure"""
    coordinate_specific: Dict[str, Any]    # Values at exact lat/lon
    area_summary: Dict[str, Any]          # Statistics across buffer area
    visualization: Optional[VisualizationData] = None
    risk_assessment: Optional[str] = None  # Fire risk category if applicable

@dataclass
class ContainerOutput:
    """Unified output format for all environmental data containers"""
    
    # Core identification (required fields first)
    source: str                      # Data source identifier
    data_type: str                   # Type of environmental data
    location: LocationInfo
    timestamp: str                   # ISO8601 request timestamp
    metadata: ProcessingMetadata
    
    # Optional fields
    event_id: Optional[str] = None   # Link to specific incident/event
    raw_data: Optional[Any] = None   # Raw binary or structured data
    interpreted_data: Optional[InterpretedData] = None
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "event_id": self.event_id,
            "source": self.source,
            "data_type": self.data_type,
            "location": {
                "latitude": self.location.latitude,
                "longitude": self.location.longitude,
                "buffer_meters": self.location.buffer_meters,
                "coordinate_system": self.location.coordinate_system
            },
            "timestamp": self.timestamp,
            "raw_data": self.raw_data,
            "interpreted_data": self.interpreted_data.__dict__ if self.interpreted_data else None,
            "metadata": self.metadata.__dict__,
            "errors": self.errors,
            "warnings": self.warnings
        }

@dataclass
class AggregatedResponse:
    """Response format for API endpoints that combine multiple containers"""
    
    # Request information
    request_id: str
    event_id: Optional[str]
    location: LocationInfo
    timestamp: str
    
    # Container outputs
    landfire: Optional[ContainerOutput] = None
    modis: Optional[ContainerOutput] = None
    weather: Optional[ContainerOutput] = None
    topography: Optional[ContainerOutput] = None
    
    # Future format containers
    pdf_data: List[ContainerOutput] = field(default_factory=list)
    excel_data: List[ContainerOutput] = field(default_factory=list)
    kml_data: List[ContainerOutput] = field(default_factory=list)
    satellite_imagery: List[ContainerOutput] = field(default_factory=list)
    
    # Summary information
    summary: Dict[str, Any] = field(default_factory=dict)
    total_processing_time_ms: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON API responses"""
        result = {
            "request_id": self.request_id,
            "event_id": self.event_id,
            "location": self.location.__dict__,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "total_processing_time_ms": self.total_processing_time_ms
        }
        
        # Add container outputs
        if self.landfire:
            result["landfire"] = self.landfire.to_dict()
        if self.modis:
            result["modis"] = self.modis.to_dict()
        if self.weather:
            result["weather"] = self.weather.to_dict()
        if self.topography:
            result["topography"] = self.topography.to_dict()
            
        # Add multi-format data
        if self.pdf_data:
            result["pdf_data"] = [item.to_dict() for item in self.pdf_data]
        if self.excel_data:
            result["excel_data"] = [item.to_dict() for item in self.excel_data]
        if self.kml_data:
            result["kml_data"] = [item.to_dict() for item in self.kml_data]
        if self.satellite_imagery:
            result["satellite_imagery"] = [item.to_dict() for item in self.satellite_imagery]
            
        return result

# Container-specific data type constants
class DataTypes:
    """Standardized data type identifiers"""
    LANDFIRE_VEGETATION = "landfire_vegetation"
    LANDFIRE_FUEL = "landfire_fuel"
    LANDFIRE_CANOPY = "landfire_canopy"
    LANDFIRE_TOPOGRAPHY = "landfire_topography"
    MODIS_VEGETATION_INDICES = "modis_vegetation_indices"
    MODIS_TEMPERATURE = "modis_temperature"
    WEATHER_CURRENT = "weather_current"
    WEATHER_FORECAST = "weather_forecast"
    TOPOGRAPHY_DEM = "topography_dem"
    PDF_EXTRACT = "pdf_extract"
    EXCEL_DATA = "excel_data"
    KML_FEATURES = "kml_features"
    SATELLITE_IMAGE = "satellite_image"

# Source identifiers
class Sources:
    """Standardized source identifiers"""
    LANDFIRE = "LANDFIRE"
    MODIS_ORNL = "MODIS_ORNL"
    OPENWEATHERMAP = "OpenWeatherMap"
    USGS_3DEP = "USGS_3DEP"
    PDF_EXTRACTOR = "PDF_Extractor"
    EXCEL_PARSER = "Excel_Parser"
    KML_PROCESSOR = "KML_Processor"
    SATELLITE_ANALYZER = "Satellite_Analyzer"

# Example usage and validation
def create_example_landfire_output() -> ContainerOutput:
    """Example of properly formatted LANDFIRE container output"""
    return ContainerOutput(
        event_id="incident-2025-001",
        source=Sources.LANDFIRE,
        data_type=DataTypes.LANDFIRE_VEGETATION,
        location=LocationInfo(
            latitude=34.0522,
            longitude=-118.2437,
            buffer_meters=1000
        ),
        timestamp=datetime.now().isoformat(),
        raw_data="b'binary_geotiff_data...'",
        interpreted_data=InterpretedData(
            coordinate_specific={
                "pixel_value": 7298,
                "vegetation_class": "Developed-Low Intensity",
                "fire_risk": "MODERATE"
            },
            area_summary={
                "dominant_class": "Developed-Low Intensity",
                "class_percentages": {
                    "Developed-Low Intensity": 45.2,
                    "California Coastal Scrub": 31.7,
                    "Developed-Medium Intensity": 23.1
                }
            },
            visualization=VisualizationData(
                arrays=[[7298, 7299], [7296, 7298]],
                legends={
                    "7298": {"name": "Developed-Low Intensity", "color": "#ff6b6b"},
                    "7299": {"name": "Developed-Medium Intensity", "color": "#cc0000"},
                    "7296": {"name": "California Coastal Scrub", "color": "#4ecdc4"}
                },
                bounds={
                    "north": 34.0572,
                    "south": 34.0472,
                    "east": -118.2387,
                    "west": -118.2487
                },
                resolution_meters=30.0
            )
        ),
        metadata=ProcessingMetadata(
            processing_time_ms=2340,
            data_currency="2024-07-15T00:00:00Z",
            retrieved_at=datetime.now().isoformat(),
            quality_score=0.95,
            container_id="landfire-processor-abc123",
            container_version="1.0.0"
        )
    )

def validate_container_output(output: ContainerOutput) -> List[str]:
    """Validate that container output conforms to schema"""
    errors = []
    
    # Required fields
    if not output.source:
        errors.append("Missing required field: source")
    if not output.data_type:
        errors.append("Missing required field: data_type")
    if not output.location:
        errors.append("Missing required field: location")
    if not output.timestamp:
        errors.append("Missing required field: timestamp")
    if not output.metadata:
        errors.append("Missing required field: metadata")
    
    # Location validation
    if output.location:
        if not (-90 <= output.location.latitude <= 90):
            errors.append("Invalid latitude: must be between -90 and 90")
        if not (-180 <= output.location.longitude <= 180):
            errors.append("Invalid longitude: must be between -180 and 180")
    
    # Quality score validation
    if output.metadata and output.metadata.quality_score:
        if not (0.0 <= output.metadata.quality_score <= 1.0):
            errors.append("Invalid quality_score: must be between 0.0 and 1.0")
    
    return errors

if __name__ == "__main__":
    # Test the schema with example data
    example = create_example_landfire_output()
    validation_errors = validate_container_output(example)
    
    if validation_errors:
        print("Schema validation errors:")
        for error in validation_errors:
            print(f"  - {error}")
    else:
        print("Schema validation passed!")
        
    # Show example JSON output
    print("\nExample container output:")
    print(json.dumps(example.to_dict(), indent=2, default=str))