"""
LANDFIRE Container Service

Containerized microservice for LANDFIRE data processing.
Handles vegetation, fuel, canopy, and topographic data with interpretation.
"""

import os
import sys
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

# Add parent directory to path to import services
sys.path.append('/app')
sys.path.append('/app/services')
sys.path.append('/app/metadata')

from shared_schema import (
    ContainerOutput, LocationInfo, ProcessingMetadata, 
    InterpretedData, VisualizationData, Sources, DataTypes
)

# Import existing services
try:
    from services.landfire_service import LANDFIREDataService
    from metadata.landfire_interpretation import LANDFIREMetadataExtractor
except ImportError as e:
    print(f"Warning: Could not import LANDFIRE services: {e}")
    LANDFIREDataService = None
    LANDFIREMetadataExtractor = None

app = FastAPI(title="LANDFIRE Container Service", version="1.0.0")

# Initialize LANDFIRE services
landfire_service = LANDFIREDataService() if LANDFIREDataService else None
metadata_extractor = LANDFIREMetadataExtractor() if LANDFIREMetadataExtractor else None

class LANDFIRERequest(BaseModel):
    """Request model for LANDFIRE data"""
    latitude: float
    longitude: float
    buffer_meters: Optional[int] = 1000
    event_id: Optional[str] = None
    layers: Optional[list] = None  # Specific layers to fetch

@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration"""
    return {
        "status": "healthy",
        "service": "landfire-container",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "aws_configured": bool(os.getenv("AWS_ACCESS_KEY_ID")),
        "interpretation_available": metadata_extractor is not None
    }

@app.post("/landfire", response_model=dict)
async def get_landfire_data(request: LANDFIRERequest):
    """
    Get LANDFIRE data for specified coordinates with interpretation
    Returns data in shared schema format
    """
    if not landfire_service:
        raise HTTPException(status_code=503, detail="LANDFIRE service not available")
    
    start_time = datetime.now()
    
    try:
        # Get raw LANDFIRE data using existing service
        landfire_data = landfire_service.get_data(
            request.latitude, 
            request.longitude, 
            request.buffer_meters
        )
        
        # Apply interpretation using Mark's coordinate-specific interpretation
        interpreted_pixels = {}
        if metadata_extractor and landfire_data.get("data"):
            for product_name, product_data in landfire_data["data"].items():
                if isinstance(product_data, dict) and "data" in product_data:
                    try:
                        interpretation = metadata_extractor.interpret_pixel_at_coordinate(
                            geotiff_bytes=product_data["data"],
                            latitude=request.latitude,
                            longitude=request.longitude,
                            product_type=product_name
                        )
                        interpreted_pixels[product_name] = interpretation
                    except Exception as e:
                        print(f"Warning: Interpretation failed for {product_name}: {e}")
        
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        # Transform to shared schema format
        location = LocationInfo(
            latitude=request.latitude,
            longitude=request.longitude,
            buffer_meters=request.buffer_meters
        )
        
        metadata = ProcessingMetadata(
            processing_time_ms=processing_time,
            data_currency="2024-01-01T00:00:00Z",  # LANDFIRE 2024 data
            retrieved_at=datetime.now().isoformat(),
            quality_score=1.0 if not landfire_data.get("errors") else 0.8,
            container_id=f"landfire-container-{os.getpid()}",
            container_version="1.0.0"
        )
        
        # Create interpreted data structure using Mark's pixel interpretations
        interpreted_data = None
        if interpreted_pixels:
            coordinate_specific = {}
            area_summary = {}
            
            # Extract coordinate-specific values from Mark's interpretation results
            for product_name, interpretation in interpreted_pixels.items():
                if "coordinate_pixel" in interpretation:
                    pixel_data = interpretation["coordinate_pixel"]
                    if product_name == "vegetation_type":
                        coordinate_specific.update({
                            "vegetation_class": pixel_data.get("interpreted"),
                            "vegetation_pixel_value": pixel_data.get("pixel_value"),
                            "vegetation_coordinates": {
                                "lat": pixel_data.get("lat"),
                                "lon": pixel_data.get("lon"),
                                "row": pixel_data.get("row"),
                                "col": pixel_data.get("col")
                            }
                        })
                    elif product_name == "fuel_model":
                        coordinate_specific.update({
                            "fuel_model_class": pixel_data.get("interpreted"),
                            "fuel_model_pixel_value": pixel_data.get("pixel_value"),
                            "fuel_coordinates": {
                                "lat": pixel_data.get("lat"),
                                "lon": pixel_data.get("lon"),
                                "row": pixel_data.get("row"),
                                "col": pixel_data.get("col")
                            }
                        })
                    elif product_name == "canopy_cover":
                        coordinate_specific.update({
                            "canopy_cover_percent": pixel_data.get("pixel_value"),
                            "canopy_cover_interpreted": pixel_data.get("interpreted")
                        })
                    elif product_name == "canopy_height":
                        coordinate_specific.update({
                            "canopy_height_meters": pixel_data.get("pixel_value"),
                            "canopy_height_interpreted": pixel_data.get("interpreted")
                        })
            
            # Create area summary showing what products were interpreted
            area_summary = {
                "interpreted_products": list(interpreted_pixels.keys()),
                "coordinate_interpretations": {
                    product: interp.get("coordinate_pixel", {}).get("interpreted", "Unknown")
                    for product, interp in interpreted_pixels.items()
                },
                "pixel_values": {
                    product: interp.get("coordinate_pixel", {}).get("pixel_value")
                    for product, interp in interpreted_pixels.items()
                }
            }
            
            # Determine fire risk based on vegetation and fuel model
            fire_risk = "UNKNOWN"
            if coordinate_specific.get("vegetation_class") and coordinate_specific.get("fuel_model_class"):
                veg_class = coordinate_specific["vegetation_class"]
                fuel_class = coordinate_specific["fuel_model_class"]
                if any(term in veg_class.lower() for term in ["developed", "urban", "water"]):
                    fire_risk = "LOW"
                elif any(term in fuel_class.lower() for term in ["chaparral", "timber", "grass"]):
                    fire_risk = "MODERATE_TO_HIGH"
                else:
                    fire_risk = "MODERATE"
            
            interpreted_data = InterpretedData(
                coordinate_specific=coordinate_specific,
                area_summary=area_summary,
                visualization=None,  # No visualization in basic implementation
                risk_assessment=fire_risk
            )
        
        # Create standardized container output
        container_output = ContainerOutput(
            source=Sources.LANDFIRE,
            data_type=DataTypes.LANDFIRE_VEGETATION,  # Primary data type
            location=location,
            timestamp=datetime.now().isoformat(),
            metadata=metadata,
            event_id=request.event_id,
            raw_data=landfire_data,
            interpreted_data=interpreted_data,
            errors=landfire_data.get("errors", [])
        )
        
        return container_output.to_dict()
        
    except Exception as e:
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        # Return error response in shared schema format
        error_output = ContainerOutput(
            source=Sources.LANDFIRE,
            data_type=DataTypes.LANDFIRE_VEGETATION,
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
                container_id=f"landfire-container-{os.getpid()}",
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
        "container": "landfire-container",
        "version": "1.0.0",
        "schema_version": "1.0.0",
        "service_available": landfire_service is not None,
        "interpretation_available": metadata_extractor is not None,
        "aws_configured": bool(os.getenv("AWS_ACCESS_KEY_ID")),
        "supported_layers": [
            "vegetation_type", "fuel_model", "canopy_cover", 
            "canopy_height", "canopy_bulk_density", "canopy_base_height",
            "slope", "aspect", "elevation"
        ],
        "endpoints": ["/health", "/landfire", "/status"]
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")