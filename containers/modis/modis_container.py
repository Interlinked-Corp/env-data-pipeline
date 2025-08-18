"""
MODIS Container Service

Containerized microservice for MODIS satellite data processing.
Handles vegetation indices, temperature, and time series analysis.
"""

import os
import sys
import json
import logging
import requests
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
import numpy as np

# Add parent directory to path to import shared modules
sys.path.append('/app')

from containers.shared_schema import (
    ContainerOutput, LocationInfo, ProcessingMetadata, 
    InterpretedData, Sources, DataTypes
)


class MODISDataService:
    """
    ORNL MODIS data access service for vegetation indices and biophysical parameters
    
    Uses the ORNL MODIS web service which provides simplified access to MODIS data
    without authentication requirements.
    
    Provides access to:
    - NDVI/EVI vegetation indices
    - LAI/FPAR biophysical parameters
    - Land surface temperature
    - Gross primary productivity
    """
    
    def __init__(self):
        """Initialize MODIS data service using ORNL web service API."""
        self.base_url = 'https://modis.ornl.gov/rst/api/v1'
        self.session = requests.Session()
        
        # Set shorter timeouts to prevent hanging
        self.session.timeout = 30
        
        # MODIS satellite data products available through ORNL service
        # Using non-versioned endpoints as primary since .061 versions are not available
        self.products = {
            'MOD13Q1': 'Terra Vegetation Indices (NDVI/EVI) 16-Day 250m',
            'MYD13Q1': 'Aqua Vegetation Indices (NDVI/EVI) 16-Day 250m',
            'MOD15A2H': 'Terra Leaf Area Index/FPAR 8-Day 500m',
            'MYD15A2H': 'Aqua Leaf Area Index/FPAR 8-Day 500m',
            'MOD11A2': 'Terra Land Surface Temperature 8-Day 1km',
            'MYD11A2': 'Aqua Land Surface Temperature 8-Day 1km',
            'MOD17A2H': 'Terra Gross Primary Productivity 8-Day 500m',
            'MYD17A2H': 'Aqua Gross Primary Productivity 8-Day 500m'
        }
    
    def get_data(self, lat: float, lon: float, days_back: int = 30) -> Dict[str, Any]:
        """
        Retrieve MODIS data for specified coordinates using ORNL web service
        
        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees
            days_back: Number of days back to search for data
            
        Returns:
            Dictionary containing MODIS data and metadata
        """
        logger = logging.getLogger(__name__)
        logger.info(f"Retrieving MODIS data from ORNL service for ({lat:.4f}, {lon:.4f})")
        
        results = {
            'source': 'MODIS_ORNL',
            'location': {'latitude': lat, 'longitude': lon},
            'search_period_days': days_back,
            'data': {},
            'errors': []
        }
        
        # Generate MODIS date range in required AYYYYDDD format
        # Calculate temporal search window from current date
        end_date = datetime.now()
        
        # Vegetation indices (MOD13Q1/MYD13Q1) require longer time windows due to 16-day composites
        # Use minimum 90 days to ensure adequate data for all products
        extended_days_back = max(days_back, 90)  # Ensure minimum 90 days for vegetation indices
        start_date = end_date - timedelta(days=extended_days_back)
        
        # Format dates for MODIS API compatibility
        start_modis = f"A{start_date.year}{start_date.timetuple().tm_yday:03d}"
        end_modis = f"A{end_date.year}{end_date.timetuple().tm_yday:03d}"
        
        logger.info(f"MODIS date range: {start_modis} to {end_modis} ({extended_days_back} days)")
        
        # Process data retrieval for all configured MODIS products
        for product, description in self.products.items():
            try:
                data = self._get_product_data(product, lat, lon, start_modis, end_modis)
                if data:
                    results['data'][product] = {
                        'description': description,
                        'data': data,
                        'retrieved_at': datetime.now().isoformat(),
                        'endpoint_used': product
                    }
                    logger.info(f"Retrieved {product}: {len(data.get('subset', []))} data points")
                else:
                    results['errors'].append(f"No data available for {product}")
                    
            except Exception as e:
                error_msg = f"Error retrieving {product}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(error_msg)
        
        return results
    
    def _get_product_data(self, product: str, lat: float, lon: float, 
                         start_date: str, end_date: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve data for a specific MODIS product using ORNL API
        
        Args:
            product: MODIS product name (e.g., 'MOD13Q1')
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees
            start_date: Start date in MODIS format (AYYYYDDD)
            end_date: End date in MODIS format (AYYYYDDD)
            
        Returns:
            Dictionary with product data or None if failed
        """
        # ORNL API parameters with reduced timeout for faster failure
        params = {
            'latitude': lat,
            'longitude': lon,
            'startDate': start_date,
            'endDate': end_date,
            'kmAboveBelow': 1,  # 1km buffer above/below
            'kmLeftRight': 1    # 1km buffer left/right
        }
        
        url = f"{self.base_url}/{product}/subset"
        
        try:
            # Use shorter timeout to prevent hanging
            response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger = logging.getLogger(__name__)
                logger.warning(f"ORNL API returned status {response.status_code} for {product}")
                logger.debug(f"Request URL: {response.url}")
                logger.debug(f"Response text: {response.text[:500]}")
                return None
                
        except requests.exceptions.Timeout:
            logger = logging.getLogger(__name__)
            logger.warning(f"Timeout requesting {product} from ORNL (30s limit)")
            return None
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Error requesting {product} from ORNL: {e}")
            return None

app = FastAPI(title="MODIS Container Service", version="1.0.0")

# Initialize MODIS service
modis_service = MODISDataService()

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