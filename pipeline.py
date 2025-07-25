"""
Main Environmental Data Pipeline

Coordinates data retrieval from multiple sources to provide comprehensive
topography, vegetation, and weather data for specified coordinates.

Uses modular service architecture with individual data source modules.
"""

import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, Any, Union, List
import logging

# Import modular services
from services import (
    LANDFIREDataService,
    MODISDataService, 
    USGSElevationService,
    OpenWeatherMapService
)

# Configuration import with fallback handling
try:
    from config import (
        MODIS_ENABLED,
        LANDFIRE_YEAR, 
        DEFAULT_BUFFER_METERS, 
        MODIS_SEARCH_DAYS,
        ENABLE_LANDFIRE,
        ENABLE_USGS_ELEVATION,
        ENABLE_MODIS,
        LOG_LEVEL
    )
    # Try to import OpenWeather API key from config
    try:
        from config import OPENWEATHER_API_KEY, OPENWEATHER_ENV
    except ImportError:
        OPENWEATHER_API_KEY = None
        OPENWEATHER_ENV = "dev"
except ImportError:
    # Default configuration values when config.py is unavailable
    MODIS_ENABLED = True
    LANDFIRE_YEAR = 2024
    DEFAULT_BUFFER_METERS = 1000
    MODIS_SEARCH_DAYS = 30
    ENABLE_LANDFIRE = True
    ENABLE_USGS_ELEVATION = True
    ENABLE_MODIS = True
    LOG_LEVEL = "INFO"
    OPENWEATHER_API_KEY = None
    OPENWEATHER_ENV = "dev"
    print("Warning: config.py not found. Using default configuration.")

# Initialize logging system
logging.basicConfig(level=getattr(logging, LOG_LEVEL))
logger = logging.getLogger(__name__)


class EnvironmentalDataPipeline:
    """
    Environmental data pipeline
    
    Coordinates data retrieval from multiple sources to provide comprehensive
    environmental data including topography, vegetation, and weather for specified coordinates.
    """
    
    def __init__(self, landfire_year: Optional[Union[int, str]] = None, weather_api_key: Optional[str] = None):
        """
        Initialize environmental data pipeline with service configuration.
        
        Args:
            landfire_year: LANDFIRE data year (uses config.py if None, auto-detects latest if 'latest')
            weather_api_key: OpenWeatherMap API key (uses config if None)
        """
        # Auto-detect latest LANDFIRE year if requested
        if landfire_year == 'latest':
            landfire_year = self._get_latest_landfire_year()
        elif landfire_year is None:
            landfire_year = LANDFIRE_YEAR
            
        # Initialize data services according to configuration settings
        self.landfire = LANDFIREDataService(landfire_year) if ENABLE_LANDFIRE else None
        self.modis = MODISDataService() if MODIS_ENABLED else None
        self.elevation = USGSElevationService() if ENABLE_USGS_ELEVATION else None
        
        # Initialize weather service if API key available
        try:
            self.weather = OpenWeatherMapService(api_key=weather_api_key) if OPENWEATHER_API_KEY or weather_api_key else None
        except ValueError as e:
            logger.warning(f"Weather service disabled: {e}")
            self.weather = None
        
        # Report active services and configuration status
        status_parts = []
        if self.landfire:
            status_parts.append(f"LANDFIRE: {landfire_year}")
        if self.modis:
            status_parts.append("MODIS: enabled (ORNL)")
        elif not MODIS_ENABLED:
            status_parts.append("MODIS: disabled")
        if self.elevation:
            status_parts.append("USGS: enabled")
        if self.weather:
            status_parts.append(f"Weather: enabled ({self.weather.environment})")
        else:
            status_parts.append("Weather: disabled")
            
        logger.info(f"Pipeline initialized - {', '.join(status_parts)}")
    
    def _get_latest_landfire_year(self) -> int:
        """
        Auto-detect the latest available LANDFIRE year
        
        Returns:
            Latest available LANDFIRE year
        """
        # Test years in descending order to find the latest available
        test_years = [2024, 2023, 2022, 2021]
        
        for year in test_years:
            try:
                test_service = LANDFIREDataService(year)
                # Test if the year's endpoint is accessible
                test_url = test_service.year_config['endpoint']
                response = requests.get(f"{test_url}?service=WCS&version=1.0.0&request=GetCapabilities", timeout=10)
                if response.status_code == 200:
                    logger.info(f"Auto-detected latest LANDFIRE year: {year}")
                    return year
            except Exception as e:
                logger.debug(f"LANDFIRE year {year} not available: {e}")
        
        # Fallback to configured year if auto-detection fails
        logger.warning("Could not auto-detect latest LANDFIRE year, using configured default")
        return LANDFIRE_YEAR
    
    def get_location_data(self, latitude: float, longitude: float, 
                         buffer_meters: Optional[int] = None) -> Dict[str, Any]:
        """
        Retrieve comprehensive geospatial data for specified coordinates
        
        Args:
            latitude: Latitude in decimal degrees (-90 to 90)
            longitude: Longitude in decimal degrees (-180 to 180)
            buffer_meters: Buffer distance around point in meters (uses config.py default if None)
            
        Returns:
            Dictionary containing all retrieved data organized by source
            
        Example:
            pipeline = EnvironmentalDataPipeline()
            data = pipeline.get_location_data(34.0522, -118.2437, buffer_meters=500)
        """
        # Apply default buffer size from configuration
        if buffer_meters is None:
            buffer_meters = DEFAULT_BUFFER_METERS
            
        # Validate coordinate and parameter inputs
        if not (-90 <= latitude <= 90):
            raise ValueError(f"Invalid latitude: {latitude}. Must be between -90 and 90.")
        
        if not (-180 <= longitude <= 180):
            raise ValueError(f"Invalid longitude: {longitude}. Must be between -180 and 180.")
        
        if buffer_meters <= 0:
            raise ValueError(f"Invalid buffer: {buffer_meters}. Must be positive.")
        
        logger.info(f"Retrieving data for location ({latitude:.4f}, {longitude:.4f}) with {buffer_meters}m buffer")
        
        # Create standardized response structure with data currency tracking
        results = {
            'request': {
                'latitude': latitude,
                'longitude': longitude, 
                'buffer_meters': buffer_meters,
                'timestamp': datetime.now().isoformat(),
                'real_time_priority': True
            },
            'landfire': {},
            'modis': {},
            'elevation': {},
            'weather': {},
            'data_currency': {
                'real_time_sources': [],
                'static_sources': [],
                'stale_data_warnings': []
            },
            'summary': {
                'total_sources': 0,
                'successful_sources': 0,
                'total_errors': 0,
                'timeliness_score': 0  # 0-100 score for data currency
            }
        }
        
        # Execute LANDFIRE data retrieval workflow
        if self.landfire:
            try:
                landfire_results = self.landfire.get_data(latitude, longitude, buffer_meters)
                results['landfire'] = landfire_results
                results['summary']['total_sources'] += 1
                
                if landfire_results['data'] and not landfire_results['errors']:
                    results['summary']['successful_sources'] += 1
                
                results['summary']['total_errors'] += len(landfire_results['errors'])
                
            except Exception as e:
                error_msg = f"LANDFIRE service error: {str(e)}"
                results['landfire'] = {'errors': [error_msg]}
                results['summary']['total_errors'] += 1
                logger.error(error_msg)
        else:
            results['landfire'] = {'info': 'LANDFIRE access disabled in configuration'}
        
        # Execute MODIS data retrieval workflow if configured
        if self.modis:
            try:
                modis_results = self.modis.get_data(latitude, longitude, MODIS_SEARCH_DAYS)
                results['modis'] = modis_results
                results['summary']['total_sources'] += 1
                
                if modis_results['data'] and not modis_results['errors']:
                    results['summary']['successful_sources'] += 1
                
                results['summary']['total_errors'] += len(modis_results['errors'])
                
            except Exception as e:
                error_msg = f"MODIS service error: {str(e)}"
                results['modis'] = {'errors': [error_msg]}
                results['summary']['total_errors'] += 1
                logger.error(error_msg)
        else:
            results['modis'] = {'info': 'MODIS access disabled in configuration'}
        
        # Execute USGS elevation data retrieval workflow
        if self.elevation:
            try:
                elevation_results = self.elevation.get_data(latitude, longitude, buffer_meters)
                results['elevation'] = elevation_results
                results['summary']['total_sources'] += 1
                
                if elevation_results['data'] and not elevation_results['errors']:
                    results['summary']['successful_sources'] += 1
                
                results['summary']['total_errors'] += len(elevation_results['errors'])
                
            except Exception as e:
                error_msg = f"Elevation service error: {str(e)}"
                results['elevation'] = {'errors': [error_msg]}
                results['summary']['total_errors'] += 1
                logger.error(error_msg)
        else:
            results['elevation'] = {'info': 'USGS elevation access disabled in configuration'}
        
        # Execute weather data retrieval workflow
        if self.weather:
            try:
                weather_results = self.weather.get_data(latitude, longitude)
                results['weather'] = weather_results
                results['summary']['total_sources'] += 1
                
                if weather_results['data'] and not weather_results['errors']:
                    results['summary']['successful_sources'] += 1
                    results['data_currency']['real_time_sources'].append('weather')
                
                results['summary']['total_errors'] += len(weather_results['errors'])
                
            except Exception as e:
                error_msg = f"Weather service error: {str(e)}"
                results['weather'] = {'errors': [error_msg]}
                results['summary']['total_errors'] += 1
                logger.error(error_msg)
        else:
            results['weather'] = {'info': 'Weather data disabled - no API key configured'}
        
        # Calculate data currency indicators
        self._calculate_data_currency(results)
        
        # Log retrieval operation summary
        logger.info(f"Data retrieval complete: {results['summary']['successful_sources']}/{results['summary']['total_sources']} sources successful, {results['summary']['total_errors']} total errors, timeliness score: {results['summary']['timeliness_score']}")
        
        return results
    
    def _calculate_data_currency(self, results: Dict[str, Any]) -> None:
        """
        Calculate data currency indicators and timeliness score
        
        Args:
            results: Results dictionary to update with currency information
        """
        currency_info = results['data_currency']
        
        # Classify data sources by update frequency
        if results['landfire'].get('data'):
            currency_info['static_sources'].append('landfire')
        
        if results['elevation'].get('data'):
            currency_info['static_sources'].append('elevation')
        
        if results['modis'].get('data'):
            # MODIS is updated regularly but not real-time
            currency_info['static_sources'].append('modis')
            
            # Check MODIS data age for staleness warnings
            modis_data = results['modis']['data']
            for product, product_data in modis_data.items():
                if 'data' in product_data and 'subset' in product_data['data']:
                    subset_data = product_data['data']['subset']
                    if subset_data:
                        # Check if most recent MODIS data is older than 16 days (typical update cycle)
                        latest_date = subset_data[-1].get('calendar_date', '')
                        if latest_date:
                            try:
                                latest_dt = datetime.strptime(latest_date, '%Y-%m-%d')
                                days_old = (datetime.now() - latest_dt).days
                                if days_old > 16:
                                    currency_info['stale_data_warnings'].append(
                                        f"MODIS {product} data is {days_old} days old (last: {latest_date})"
                                    )
                            except ValueError:
                                pass
        
        # Weather data is real-time (already added above)
        
        # Calculate timeliness score (0-100)
        score = 0
        
        # Real-time sources get full points (25 each)
        real_time_count = len(currency_info['real_time_sources'])
        score += real_time_count * 25
        
        # Static but recent sources get partial points (15 each)
        static_count = len(currency_info['static_sources'])
        score += static_count * 15
        
        # Penalize for stale data warnings (-10 each)
        stale_warnings = len(currency_info['stale_data_warnings'])
        score -= stale_warnings * 10
        
        # Ensure score stays within 0-100 range
        results['summary']['timeliness_score'] = max(0, min(100, score))


def example_usage():
    """Demonstrate environmental data pipeline functionality with sample coordinates."""
    
    print("Environmental Data Pipeline - Example Usage")
    print("="*50)
    
    # Initialize pipeline with configuration settings
    pipeline = EnvironmentalDataPipeline()
    
    # Test coordinates for Los Angeles, California
    latitude = 34.0522
    longitude = -118.2437
    
    # Execute data retrieval with configured parameters
    data = pipeline.get_location_data(latitude, longitude)
    
    # Output retrieval results summary
    print(f"\nData Summary for ({latitude}, {longitude}):")
    print(f"  LANDFIRE data: {len(data['landfire'].get('data', {}))} products")
    print(f"  MODIS data: {len(data['modis'].get('data', {}))} product types")
    print(f"  Elevation data: {'Available' if data['elevation'].get('data') else 'Not available'}")
    print(f"  Weather data: {'Available' if data['weather'].get('data') else 'Not available'}")
    print(f"  Total errors: {data['summary']['total_errors']}")
    
    return data


if __name__ == "__main__":
    # Execute demonstration workflow
    example_data = example_usage()