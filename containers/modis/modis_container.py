"""
MODIS Container Service

Containerized microservice for MODIS satellite data processing.
Handles vegetation indices, temperature, and time series analysis.
"""

import os
import sys
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import numpy as np

# Add parent directory to path to import services
sys.path.append('/app')
sys.path.append('/app/services')

from shared_schema import (
    ContainerOutput, LocationInfo, ProcessingMetadata, 
    InterpretedData, Sources, DataTypes
)

# Import existing services
try:
    from services.modis_service import MODISDataService
except ImportError as e:
    print(f"Warning: Could not import MODIS service: {e}")
    MODISDataService = None

app = FastAPI(title="MODIS Container Service", version="1.0.0")

# Initialize MODIS service
modis_service = MODISDataService() if MODISDataService else None

class MODISRequest(BaseModel):
    """Request model for MODIS data"""
    latitude: float
    longitude: float
    search_period_days: Optional[int] = 30
    event_id: Optional[str] = None
    products: Optional[List[str]] = None  # Specific MODIS products to fetch

@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration"""
    return {
        "status": "healthy",
        "service": "modis-container",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "ornl_service_available": modis_service is not None
    }

@app.post("/modis", response_model=dict)
async def get_modis_data(request: MODISRequest):
    """
    Get MODIS satellite data for specified coordinates
    Returns data in shared schema format with vegetation health analysis
    """
    if not modis_service:
        raise HTTPException(status_code=503, detail="MODIS service not available")
    
    start_time = datetime.now()
    
    try:
        # Get MODIS data using existing service
        modis_data = modis_service.get_data(
            request.latitude, 
            request.longitude, 
            request.search_period_days
        )
        
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        # Transform to shared schema format
        location = LocationInfo(
            latitude=request.latitude,
            longitude=request.longitude
        )
        
        metadata = ProcessingMetadata(
            processing_time_ms=processing_time,
            data_currency=datetime.now().isoformat(),  # MODIS is regularly updated
            retrieved_at=datetime.now().isoformat(),
            quality_score=1.0 if not modis_data.get("errors") else 0.8,
            container_id=f"modis-container-{os.getpid()}",
            container_version="1.0.0"
        )
        
        # Process MODIS data for interpretation
        interpreted_data = None
        if modis_data.get("data"):
            coordinate_specific = {}
            area_summary = {}
            
            # Process MOD13Q1 (Vegetation Indices) - this is already meaningful data
            if "MOD13Q1" in modis_data["data"] and modis_data["data"]["MOD13Q1"].get("data", {}).get("subset"):
                vegetation_data = modis_data["data"]["MOD13Q1"]["data"]["subset"]
                
                # Extract latest NDVI and EVI values
                latest_ndvi = None
                latest_evi = None
                latest_date = None
                
                for entry in vegetation_data:
                    if entry.get("band") == "250m_16_days_NDVI" and entry.get("data"):
                        # MODIS NDVI values need scaling (typically divided by 10000)
                        raw_values = entry["data"]
                        if raw_values and len(raw_values) > 0:
                            # Get center pixel value (middle of 9x9 grid)
                            center_idx = len(raw_values) // 2
                            scaled_ndvi = raw_values[center_idx] * 0.0001
                            if -1.0 <= scaled_ndvi <= 1.0:  # Valid NDVI range
                                latest_ndvi = scaled_ndvi
                                latest_date = entry.get("calendar_date")
                
                # Calculate vegetation health
                vegetation_health = "UNKNOWN"
                fire_risk_vegetation = "UNKNOWN"
                
                if latest_ndvi is not None:
                    if latest_ndvi > 0.6:
                        vegetation_health = "HEALTHY"
                        fire_risk_vegetation = "LOW"
                    elif latest_ndvi > 0.3:
                        vegetation_health = "MODERATE"
                        fire_risk_vegetation = "MODERATE" 
                    elif latest_ndvi > 0.1:
                        vegetation_health = "STRESSED"
                        fire_risk_vegetation = "HIGH"
                    else:
                        vegetation_health = "SEVERELY_STRESSED"
                        fire_risk_vegetation = "EXTREME"
                
                coordinate_specific.update({
                    "ndvi_latest": latest_ndvi,
                    "evi_latest": latest_evi,
                    "vegetation_health": vegetation_health,
                    "fire_risk_vegetation": fire_risk_vegetation,
                    "last_observation_date": latest_date
                })
            
            # Process MOD11A2 (Temperature) if available
            if "MOD11A2" in modis_data["data"] and modis_data["data"]["MOD11A2"].get("data", {}).get("subset"):
                temp_data = modis_data["data"]["MOD11A2"]["data"]["subset"]
                
                latest_temp = None
                for entry in temp_data:
                    if entry.get("band") == "LST_Day_1km" and entry.get("data"):
                        raw_values = entry["data"]
                        if raw_values and len(raw_values) > 0:
                            center_idx = len(raw_values) // 2
                            # MODIS LST scaling: multiply by 0.02, subtract 273.15
                            temp_kelvin = raw_values[center_idx] * 0.02
                            temp_celsius = temp_kelvin - 273.15
                            if -50 <= temp_celsius <= 60:  # Reasonable temperature range
                                latest_temp = temp_celsius
                                break
                
                if latest_temp is not None:
                    coordinate_specific["land_surface_temperature_c"] = latest_temp
            
            # Create area summary with time series analysis
            total_observations = 0
            for product_name, product_data in modis_data["data"].items():
                if product_data.get("data", {}).get("subset"):
                    total_observations += len(product_data["data"]["subset"])
            
            area_summary = {
                "total_observations": total_observations,
                "search_period_days": request.search_period_days,
                "data_quality": "GOOD" if total_observations > 10 else "LIMITED",
                "products_available": list(modis_data["data"].keys())
            }
            
            interpreted_data = InterpretedData(
                coordinate_specific=coordinate_specific,
                area_summary=area_summary,
                risk_assessment=coordinate_specific.get("fire_risk_vegetation", "UNKNOWN")
            )
        
        # Create standardized container output
        container_output = ContainerOutput(
            source=Sources.MODIS_ORNL,
            data_type=DataTypes.MODIS_VEGETATION_INDICES,
            location=location,
            timestamp=datetime.now().isoformat(),
            metadata=metadata,
            event_id=request.event_id,
            raw_data=modis_data,
            interpreted_data=interpreted_data,
            errors=modis_data.get("errors", [])
        )
        
        return container_output.to_dict()
        
    except Exception as e:
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        # Return error response in shared schema format
        error_output = ContainerOutput(
            source=Sources.MODIS_ORNL,
            data_type=DataTypes.MODIS_VEGETATION_INDICES,
            location=LocationInfo(latitude=request.latitude, longitude=request.longitude),
            timestamp=datetime.now().isoformat(),
            metadata=ProcessingMetadata(
                processing_time_ms=processing_time,
                data_currency=datetime.now().isoformat(),
                retrieved_at=datetime.now().isoformat(),
                quality_score=0.0,
                container_id=f"modis-container-{os.getpid()}",
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
        "container": "modis-container",
        "version": "1.0.0", 
        "schema_version": "1.0.0",
        "service_available": modis_service is not None,
        "ornl_service": "https://modisrest.ornl.gov/rst/api/v1/",
        "supported_products": [
            "MOD13Q1", "MYD13Q1",  # Vegetation Indices
            "MOD15A2H", "MYD15A2H", # LAI/FPAR
            "MOD11A2", "MYD11A2",   # Temperature
            "MOD17A2H", "MYD17A2H"  # GPP/NPP
        ],
        "endpoints": ["/health", "/modis", "/status"]
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8002))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")