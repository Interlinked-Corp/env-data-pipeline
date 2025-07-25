"""
LANDFIRE Data Service

Provides access to LANDFIRE vegetation and fuel characteristics data including:
- Vegetation types and characteristics
- Fire behavior fuel models
- Canopy structure data
- Topographic products (slope, aspect, elevation)
"""

import requests
from datetime import datetime
from typing import Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


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
            logger.error(f"WCS request failed for {layer_name}: {e}")
            return None