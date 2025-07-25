"""
USGS Elevation Service

Provides access to USGS 3DEP elevation data for topographic information including:
- Digital elevation models
- Derived terrain products (slope, aspect)
"""

import requests
from datetime import datetime
from typing import Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


class USGSElevationService:
    """
    USGS 3DEP elevation data service for topographic information
    
    Provides access to:
    - Digital elevation models
    - Derived terrain products (slope, aspect)
    """
    
    def __init__(self):
        """Initialize USGS 3DEP elevation data service."""
        self.endpoint = 'https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer'
    
    def get_data(self, lat: float, lon: float, buffer_meters: int = 1000) -> Dict[str, Any]:
        """
        Retrieve topographic data for specified coordinates
        
        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees
            buffer_meters: Buffer distance around point in meters
            
        Returns:
            Dictionary containing elevation, slope, and aspect data
        """
        logger.info(f"Retrieving topographic data for ({lat:.4f}, {lon:.4f})")
        
        results = {
            'source': 'USGS_3DEP',
            'location': {'latitude': lat, 'longitude': lon},
            'buffer_meters': buffer_meters,
            'data': {},
            'errors': []
        }
        
        try:
            # Transform coordinates to Web Mercator projection for accurate buffer calculation
            try:
                from pyproj import Transformer
                transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
                center_x, center_y = transformer.transform(lon, lat)
                bbox = f"{center_x-buffer_meters},{center_y-buffer_meters},{center_x+buffer_meters},{center_y+buffer_meters}"
                bbox_sr = 3857
            except ImportError:
                # Fallback to approximate degree-based buffer calculation
                buffer_deg = buffer_meters / 111000
                bbox = f"{lon-buffer_deg},{lat-buffer_deg},{lon+buffer_deg},{lat+buffer_deg}"
                bbox_sr = 4326
            
            # Execute elevation data request as primary topographic product
            elevation_data = self._request_elevation(bbox, bbox_sr)
            if elevation_data:
                results['data']['elevation'] = elevation_data
                logger.info(f"Retrieved elevation data: {elevation_data['size_bytes']} bytes")
                
                # Note: Slope and aspect derivatives require raster processing from elevation data
                # Current implementation provides elevation as primary topographic product
                # Enhancement opportunity: implement slope/aspect calculation from elevation raster
                
            else:
                results['errors'].append("Failed to retrieve elevation data")
                
        except Exception as e:
            error_msg = f"Error retrieving topographic data: {str(e)}"
            results['errors'].append(error_msg)
            logger.error(error_msg)
        
        return results
    
    def _request_elevation(self, bbox: str, bbox_sr: int) -> Optional[Dict[str, Any]]:
        """Execute USGS ImageServer exportImage request for elevation data"""
        
        params = {
            'f': 'image',
            'bbox': bbox,
            'bboxSR': bbox_sr,
            'imageSR': 4326,
            'size': '256,256',
            'format': 'tiff',
            'pixelType': 'F32',
            'interpolation': 'RSP_BilinearInterpolation'
        }
        
        try:
            response = requests.get(f"{self.endpoint}/exportImage", params=params, timeout=60)
            
            if response.status_code == 200:
                return {
                    'data': response.content,
                    'bbox': bbox,
                    'size_bytes': len(response.content),
                    'format': 'GeoTIFF',
                    'crs': 'EPSG:4326'
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Elevation request failed: {e}")
            return None