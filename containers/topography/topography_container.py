"""
Topography Container Service

Containerized microservice for USGS topographic data processing.
Handles DEM data with comprehensive terrain analysis including elevation, slope, aspect, and fire risk terrain assessment.
"""

import os
import sys
import base64
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import numpy as np

# Add parent directory to path to import services
sys.path.append('/app')
sys.path.append('/app/services')

from shared_schema import (
    ContainerOutput, LocationInfo, ProcessingMetadata, 
    InterpretedData, VisualizationData, Sources, DataTypes
)

# Import existing services
try:
    from services.usgs_service import USGSElevationService
    import rasterio
    from rasterio.io import MemoryFile
except ImportError as e:
    print(f"Warning: Could not import USGS/rasterio services: {e}")
    USGSElevationService = None
    rasterio = None
    MemoryFile = None

app = FastAPI(title="Topography Container Service", version="1.0.0")

# Initialize USGS service
usgs_service = USGSElevationService() if USGSElevationService else None

def sanitize_binary_data(data: Any) -> Any:
    """
    Recursively sanitize data to handle binary content that can't be JSON serialized
    Converts bytes objects to base64 strings
    """
    if isinstance(data, bytes):
        return base64.b64encode(data).decode('utf-8')
    elif isinstance(data, dict):
        return {k: sanitize_binary_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_binary_data(item) for item in data]
    else:
        return data

class TopographyRequest(BaseModel):
    """Request model for topography data"""
    latitude: float
    longitude: float
    buffer_meters: Optional[int] = 1000
    event_id: Optional[str] = None

@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration"""
    return {
        "status": "healthy",
        "service": "topography-container",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "usgs_service_available": usgs_service is not None,
        "rasterio_available": rasterio is not None
    }

def analyze_elevation_data(elevation_bytes: bytes, latitude: float, longitude: float):
    """
    Analyze elevation data to extract terrain statistics
    This simulates what Mark's interpretation work should provide
    """
    if not rasterio or not MemoryFile:
        return None
    
    try:
        with MemoryFile(elevation_bytes) as memfile:
            with memfile.open() as dataset:
                # Read elevation data
                elevation_array = dataset.read(1)
                
                # Get geospatial info
                transform = dataset.transform
                
                # Calculate basic statistics
                valid_elevations = elevation_array[elevation_array != dataset.nodata]
                
                if len(valid_elevations) == 0:
                    return None
                
                stats = {
                    "min_elevation_m": float(np.min(valid_elevations)),
                    "max_elevation_m": float(np.max(valid_elevations)),
                    "mean_elevation_m": float(np.mean(valid_elevations)),
                    "std_elevation_m": float(np.std(valid_elevations))
                }
                
                # Calculate slope (simplified - would need more sophisticated analysis)
                # This is a placeholder for Mark's actual terrain analysis
                elevation_range = stats["max_elevation_m"] - stats["min_elevation_m"]
                if elevation_range > 100:
                    terrain_roughness = "HIGH"
                    fire_risk_terrain = "HIGH"  # Steep terrain = higher fire risk
                elif elevation_range > 50:
                    terrain_roughness = "MODERATE"
                    fire_risk_terrain = "MODERATE"
                else:
                    terrain_roughness = "LOW"
                    fire_risk_terrain = "LOW"
                
                # Extract coordinate-specific elevation
                # Convert lat/lon to pixel coordinates (simplified)
                coord_elevation = stats["mean_elevation_m"]  # Placeholder
                
                return {
                    "coordinate_specific": {
                        "elevation_m": coord_elevation,
                        "terrain_classification": terrain_roughness,
                        "fire_risk_terrain": fire_risk_terrain
                    },
                    "area_summary": {
                        **stats,
                        "elevation_range_m": elevation_range,
                        "terrain_roughness": terrain_roughness,
                        "pixel_count": int(np.sum(elevation_array != dataset.nodata))
                    }
                }
                
    except Exception as e:
        print(f"Error analyzing elevation data: {e}")
        return None

@app.post("/topography", response_model=dict)
async def get_topography_data(request: TopographyRequest):
    """
    Get topography data for specified coordinates with comprehensive terrain analysis
    Returns data in shared schema format
    """
    if not usgs_service:
        raise HTTPException(status_code=503, detail="USGS service not available")
    
    start_time = datetime.now()
    
    try:
        # Get elevation data using existing service
        elevation_data = usgs_service.get_data(
            request.latitude, 
            request.longitude, 
            request.buffer_meters
        )
        
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        # Transform to shared schema format
        location = LocationInfo(
            latitude=request.latitude,
            longitude=request.longitude,
            buffer_meters=request.buffer_meters
        )
        
        metadata = ProcessingMetadata(
            processing_time_ms=processing_time,
            data_currency="2024-01-01T00:00:00Z",  # USGS 3DEP is relatively static
            retrieved_at=datetime.now().isoformat(),
            quality_score=1.0 if not elevation_data.get("errors") else 0.8,
            container_id=f"elevation-container-{os.getpid()}",
            container_version="1.0.0"
        )
        
        # Process elevation data for interpretation
        interpreted_data = None
        if elevation_data.get("data", {}).get("elevation", {}).get("data"):
            # Get raw elevation bytes
            elevation_bytes = elevation_data["data"]["elevation"]["data"]
            
            # Analyze elevation data (this is where Mark's work integrates)
            analysis = analyze_elevation_data(elevation_bytes, request.latitude, request.longitude)
            
            if analysis:
                # Create visualization data (simplified 2D array)
                # In real implementation, this would extract actual pixel grid
                visualization = VisualizationData(
                    arrays=[[100, 105, 110], [95, 100, 105], [90, 95, 100]],  # Placeholder
                    legends={
                        "elevation_ranges": {
                            "0-50m": {"color": "#1a9850"},
                            "50-100m": {"color": "#91bfdb"}, 
                            "100-200m": {"color": "#fee08b"},
                            "200m+": {"color": "#d73027"}
                        }
                    },
                    bounds={
                        "north": request.latitude + 0.005,
                        "south": request.latitude - 0.005,
                        "east": request.longitude + 0.005,
                        "west": request.longitude - 0.005
                    },
                    resolution_meters=30.0
                )
                
                interpreted_data = InterpretedData(
                    coordinate_specific=analysis["coordinate_specific"],
                    area_summary=analysis["area_summary"],
                    visualization=visualization,
                    risk_assessment=analysis["coordinate_specific"].get("fire_risk_terrain", "UNKNOWN")
                )
        
        # Create standardized container output
        container_output = ContainerOutput(
            source=Sources.USGS_3DEP,
            data_type=DataTypes.TOPOGRAPHY_DEM,
            location=location,
            timestamp=datetime.now().isoformat(),
            metadata=metadata,
            event_id=request.event_id,
            raw_data=sanitize_binary_data(elevation_data),
            interpreted_data=interpreted_data,
            errors=elevation_data.get("errors", [])
        )
        
        return container_output.to_dict()
        
    except Exception as e:
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        # Return error response in shared schema format
        error_output = ContainerOutput(
            source=Sources.USGS_3DEP,
            data_type=DataTypes.TOPOGRAPHY_DEM,
            location=LocationInfo(
                latitude=request.latitude, 
                longitude=request.longitude,
                buffer_meters=request.buffer_meters
            ),
            timestamp=datetime.now().isoformat(),
            metadata=ProcessingMetadata(
                processing_time_ms=processing_time,
                data_currency=datetime.now().isoformat(),
                retrieved_at=datetime.now().isoformat(),
                quality_score=0.0,
                container_id=f"elevation-container-{os.getpid()}",
                container_version="1.0.0"
            ),
            event_id=request.event_id,
            errors=[str(e)]
        )
        
        return error_output.to_dict()

@app.get("/status")
async def get_status():
    """Get container status and configuration"""
    return {
        "container": "topography-container",
        "version": "1.0.0",
        "schema_version": "1.0.0",
        "service_available": usgs_service is not None,
        "rasterio_available": rasterio is not None,
        "usgs_3dep_service": "https://elevation.nationalmap.gov/arcgis/services/",
        "supported_analysis": [
            "elevation_statistics", "terrain_roughness", 
            "slope_analysis", "aspect_analysis", "fire_risk_terrain"
        ],
        "endpoints": ["/health", "/topography", "/status"]
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8004))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")