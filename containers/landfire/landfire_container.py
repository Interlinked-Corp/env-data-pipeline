"""
LANDFIRE Container Service

Containerized microservice for LANDFIRE data processing.
Handles vegetation, fuel, canopy, and topographic data with interpretation.
"""

import os
import sys
import base64
import logging
import requests
import rasterio
from io import BytesIO
from datetime import datetime
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

# Add parent directory to path to import shared modules
sys.path.append('/app')
sys.path.append('/app/metadata')

from containers.shared_schema import (
    ContainerOutput, LocationInfo, ProcessingMetadata, 
    InterpretedData, VisualizationData, Sources, DataTypes
)

# Import additional dependencies for metadata extraction
try:
    import boto3
    import csv
    from io import StringIO
except ImportError as e:
    print(f"Warning: Could not import metadata dependencies: {e}")
    boto3 = None


class LANDFIREMetadataExtractor:
    """
    LANDFIRE metadata extraction and pixel value interpretation
    Consolidated into container for self-contained operation
    """
    
    def __init__(self, s3_bucket: str = "env-data-prod", s3_region: str = "us-east-2"):
        """Initialize LANDFIRE metadata extractor with S3 configuration."""
        self.s3_bucket = s3_bucket
        self.s3_region = s3_region
        
        # Initialize S3 client with error handling
        try:
            if boto3:
                self.s3_client = boto3.client('s3', region_name=s3_region)
                self.s3_available = True
            else:
                self.s3_client = None
                self.s3_available = False
        except Exception as e:
            print(f"S3 client initialization failed: {e}")
            self.s3_client = None
            self.s3_available = False
        
        # Cache for downloaded attribute tables
        self._attribute_cache = {}
        
        # Fallback categories when S3 is unavailable
        self._fallback_values = {
            'vegetation_type': {
                range(7000, 8000): 'Urban/Developed',
                range(6000, 7000): 'Agriculture/Cropland',
                range(3000, 4000): 'Forest',
                range(2000, 3000): 'Grassland',
                range(4000, 5000): 'Shrubland',
                'default': 'Unknown Vegetation Type'
            },
            'fuel_model': {
                range(90, 100): 'Non-burnable',
                range(100, 110): 'Grass',
                range(110, 130): 'Timber',
                range(140, 150): 'Shrub',
                'default': 'Unknown Fuel Model'
            }
        }
    
    def interpret_pixel_at_coordinate(self, geotiff_bytes: bytes, lat: float, lon: float, product_type: str) -> Dict[str, Any]:
        """Extract pixel value at specific coordinate and interpret it."""
        try:
            with rasterio.open(BytesIO(geotiff_bytes)) as dataset:
                # Convert lat/lon to pixel coordinates
                row, col = rasterio.transform.rowcol(dataset.transform, lon, lat)
                
                # Extract pixel value
                pixel_array = dataset.read(1)
                if 0 <= row < pixel_array.shape[0] and 0 <= col < pixel_array.shape[1]:
                    pixel_value = int(pixel_array[row, col])
                    
                    # Interpret the value
                    interpreted = self._interpret_single_value(pixel_value, product_type)
                    
                    return {
                        "coordinate_pixel": {
                            "lat": lat,
                            "lon": lon,
                            "row": row,
                            "col": col,
                            "pixel_value": pixel_value,
                            "interpreted": interpreted,
                            "crs": str(dataset.crs)
                        }
                    }
                else:
                    return {"error": "Coordinates outside raster bounds"}
                    
        except Exception as e:
            return {"error": f"Pixel extraction failed: {str(e)}"}
    
    def _interpret_single_value(self, pixel_value: int, product_type: str) -> str:
        """Interpret a single pixel value using fallback mappings."""
        fallback_map = self._fallback_values.get(product_type, {})
        
        # Check direct value match first
        if pixel_value in fallback_map:
            return fallback_map[pixel_value]
        
        # Check range matches
        for key, label in fallback_map.items():
            if isinstance(key, range) and pixel_value in key:
                return label
        
        # Return default or unknown
        return fallback_map.get('default', f'Unknown ({pixel_value})')


class LANDFIREDataService:
    """
    LANDFIRE data access service for vegetation and fuel characteristics
    
    Provides access to:
    - Vegetation types and characteristics
    - Fire behavior fuel models
    - Canopy structure data
    """
    
    def __init__(self, year: int = 2024):
        """
        Initialize LANDFIRE service
        
        Args:
            year: LANDFIRE data year (2024, 2023, or 2022)
        """
        self.year = year
        
        # LANDFIRE WCS endpoint configuration by year
        self.config = {
            2024: {
                'code': '24',
                'resolution': '250',
                'endpoint': 'https://edcintl.cr.usgs.gov/geoserver/landfire_wcs/us_250/wcs'
            },
            2023: {
                'code': '23', 
                'resolution': '240',
                'endpoint': 'https://edcintl.cr.usgs.gov/geoserver/landfire_wcs/us_240/wcs'
            },
            2022: {
                'code': '22',
                'resolution': '230', 
                'endpoint': 'https://edcintl.cr.usgs.gov/geoserver/landfire_wcs/us_230/wcs'
            }
        }
        
        if year not in self.config:
            raise ValueError(f"Unsupported LANDFIRE year: {year}. Available: {list(self.config.keys())}")
        
        self.year_config = self.config[year]
        
        # LANDFIRE vegetation and fuel model products
        self.products = {
            'vegetation_type': f'landfire_wcs__LC{self.year_config["code"]}_EVT_{self.year_config["resolution"]}',
            'fuel_model': f'landfire_wcs__LC{self.year_config["code"]}_F40_{self.year_config["resolution"]}',
            'canopy_cover': f'landfire_wcs__LC{self.year_config["code"]}_CC_{self.year_config["resolution"]}',
            'canopy_height': f'landfire_wcs__LC{self.year_config["code"]}_CH_{self.year_config["resolution"]}',
            'canopy_bulk_density': f'landfire_wcs__LC{self.year_config["code"]}_CBD_{self.year_config["resolution"]}',
            'canopy_base_height': f'landfire_wcs__LC{self.year_config["code"]}_CBH_{self.year_config["resolution"]}'
        }
        
        # Topographic products from dedicated endpoint (2020 baseline)
        self.topo_endpoint = 'https://edcintl.cr.usgs.gov/geoserver/landfire_wcs/us_topo/wcs'
        self.topo_products = {
            'slope': 'landfire_wcs__LC20_SlpD_220',
            'aspect': 'landfire_wcs__LC20_Asp_220',
            'elevation': 'landfire_wcs__LC20_Elev_220'
        }
    
    def get_data(self, lat: float, lon: float, buffer_meters: int = 1000) -> Dict[str, Any]:
        """
        Retrieve LANDFIRE data for specified coordinates
        
        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees  
            buffer_meters: Buffer distance around point in meters
            
        Returns:
            Dictionary containing retrieved data or error information
        """
        logger = logging.getLogger(__name__)
        logger.info(f"Retrieving LANDFIRE {self.year} data for ({lat:.4f}, {lon:.4f})")
        
        results = {
            'source': 'LANDFIRE',
            'year': self.year,
            'location': {'latitude': lat, 'longitude': lon},
            'buffer_meters': buffer_meters,
            'data': {},
            'errors': []
        }
        
        # Convert buffer distance from meters to decimal degrees
        buffer_deg = buffer_meters / 111000
        
        # Retrieve vegetation and fuel model data from primary endpoint
        for product_name, layer_name in self.products.items():
            try:
                data = self._request_coverage(layer_name, lat, lon, buffer_deg, self.year_config['endpoint'])
                if data:
                    results['data'][product_name] = data
                    logger.info(f"Retrieved {product_name}: {data['size_bytes']} bytes")
                else:
                    results['errors'].append(f"No data available for {product_name}")
                    
            except Exception as e:
                error_msg = f"Error retrieving {product_name}: {str(e)}"
                results['errors'].append(error_msg) 
                logger.error(error_msg)
        
        # Retrieve topographic data from specialized endpoint
        for product_name, layer_name in self.topo_products.items():
            try:
                data = self._request_coverage(layer_name, lat, lon, buffer_deg, self.topo_endpoint)
                if data:
                    results['data'][product_name] = data
                    logger.info(f"Retrieved {product_name}: {data['size_bytes']} bytes")
                else:
                    results['errors'].append(f"No topographic data available for {product_name}")
                    
            except Exception as e:
                error_msg = f"Error retrieving topographic {product_name}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(error_msg)
        
        return results
    
    def _request_coverage(self, layer_name: str, lat: float, lon: float, buffer_deg: float, endpoint: str) -> Optional[Dict[str, Any]]:
        """Execute WCS GetCoverage request for specified layer and coordinates"""
        
        # Calculate geographic bounding box for coverage request
        bbox = f'{lon-buffer_deg},{lat-buffer_deg},{lon+buffer_deg},{lat+buffer_deg}'
        
        # WCS 1.0.0 GetCoverage request parameters
        params = {
            'service': 'WCS',
            'version': '1.0.0',
            'request': 'GetCoverage',
            'coverage': f'landfire_wcs:{layer_name.split("__")[1]}',
            'bbox': bbox,
            'crs': 'EPSG:4326',
            'format': 'GeoTIFF',
            'width': '256',
            'height': '256'
        }
        
        try:
            response = requests.get(endpoint, params=params, timeout=60)
            
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '')
                
                if 'image' in content_type or 'tiff' in content_type:
                    return {
                        'data': response.content,
                        'layer_name': layer_name,
                        'bbox': [lon-buffer_deg, lat-buffer_deg, lon+buffer_deg, lat+buffer_deg],
                        'size_bytes': len(response.content),
                        'format': 'GeoTIFF',
                        'crs': 'EPSG:4326'
                    }
            
            return None
            
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"WCS request failed for {layer_name}: {e}")
            return None

app = FastAPI(title="LANDFIRE Container Service", version="1.0.0")

# Initialize LANDFIRE services
landfire_service = LANDFIREDataService() if LANDFIREDataService else None
# Initialize metadata extractor with consolidated class
try:
    metadata_extractor = LANDFIREMetadataExtractor()
except Exception as e:
    print(f"Warning: Could not initialize metadata extractor: {e}")
    metadata_extractor = None

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
                            lat=request.latitude,
                            lon=request.longitude,
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
            raw_data=sanitize_binary_data(landfire_data),
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