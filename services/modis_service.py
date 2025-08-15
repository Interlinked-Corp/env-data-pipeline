"""
MODIS Data Service

Provides access to ORNL MODIS data for vegetation indices and biophysical parameters including:
- NDVI/EVI vegetation indices
- LAI/FPAR biophysical parameters  
- Land surface temperature
- Gross primary productivity

Uses optimized 90-day lookback for vegetation indices to ensure data availability.
"""

import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, List
import logging

logger = logging.getLogger(__name__)


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
                logger.warning(f"ORNL API returned status {response.status_code} for {product}")
                logger.debug(f"Request URL: {response.url}")
                logger.debug(f"Response text: {response.text[:500]}")
                return None
                
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout requesting {product} from ORNL (30s limit)")
            return None
        except Exception as e:
            logger.error(f"Error requesting {product} from ORNL: {e}")
            return None