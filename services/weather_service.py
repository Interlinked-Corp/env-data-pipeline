"""
OpenWeatherMap Weather Service

Provides access to real-time weather conditions and forecasts including:
- Current weather conditions (temperature, humidity, pressure, wind)
- Weather descriptions and forecasts  
- Fire weather-relevant parameters
"""

import requests
from datetime import datetime
from typing import Dict, Optional, Any, List
import logging

logger = logging.getLogger(__name__)


class OpenWeatherMapService:
    """
    OpenWeatherMap weather data service for real-time weather conditions
    
    Provides access to:
    - Current weather conditions (temperature, humidity, pressure, wind)
    - Weather descriptions and forecasts
    - Fire weather-relevant parameters
    """
    
    def __init__(self, api_key: Optional[str] = None, environment: str = "dev"):
        """
        Initialize OpenWeatherMap service
        
        Args:
            api_key: OpenWeatherMap API key (required - pass directly or via config)
            environment: Environment identifier for logging purposes
        """
        # Get API key from environment or parameter
        import os
        env_api_key = os.getenv('OPENWEATHER_API_KEY')
        
        self.environment = environment
        self.api_key = api_key or env_api_key
        
        if not self.api_key:
            raise ValueError(f"OpenWeatherMap API key required. Set OPENWEATHER_API_KEY environment variable or pass api_key parameter.")
        
        self.base_url = "https://api.openweathermap.org/data/2.5"
        self.session = requests.Session()
        
        logger.info(f"OpenWeatherMap service initialized for {environment} environment")
    
    def get_data(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        Retrieve current weather data for specified coordinates
        
        Args:
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees
            
        Returns:
            Dictionary containing current weather data and metadata
        """
        logger.info(f"Retrieving weather data for ({lat:.4f}, {lon:.4f})")
        
        results = {
            'source': 'OpenWeatherMap',
            'location': {'latitude': lat, 'longitude': lon},
            'data': {},
            'errors': []
        }
        
        try:
            # Get current weather conditions
            current_weather = self._get_current_weather(lat, lon)
            if current_weather:
                results['data']['current'] = self._parse_weather_data(current_weather)
                logger.info(f"Retrieved current weather: {results['data']['current']['temperature_celsius']}°C")
            else:
                results['errors'].append("Failed to retrieve current weather data")
            
            # Get 5-day forecast for fire weather planning
            forecast_data = self._get_forecast(lat, lon)
            if forecast_data:
                results['data']['forecast'] = self._parse_forecast_data(forecast_data)
                logger.info(f"Retrieved 5-day forecast: {len(results['data']['forecast'])} data points")
            else:
                results['errors'].append("Failed to retrieve weather forecast")
                
        except Exception as e:
            error_msg = f"Error retrieving weather data: {str(e)}"
            results['errors'].append(error_msg)
            logger.error(error_msg)
        
        return results
    
    def _get_current_weather(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Get current weather conditions from OpenWeatherMap API"""
        url = f"{self.base_url}/weather"
        params = {
            "lat": lat,
            "lon": lon,
            "appid": self.api_key,
            "units": "metric"
        }
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Current weather request failed: {e}")
            return None
    
    def _get_forecast(self, lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Get 5-day weather forecast from OpenWeatherMap API"""
        url = f"{self.base_url}/forecast"
        params = {
            "lat": lat,
            "lon": lon,
            "appid": self.api_key,
            "units": "metric"
        }
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Weather forecast request failed: {e}")
            return None
    
    def _parse_weather_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse current weather data into standardized format"""
        return {
            "timestamp": datetime.fromtimestamp(data['dt']).isoformat(),
            "temperature_celsius": data['main']['temp'],
            "humidity_percent": data['main']['humidity'],
            "pressure_hpa": data['main']['pressure'],
            "wind_speed_mps": data['wind'].get('speed', 0),
            "wind_direction_deg": data['wind'].get('deg', 0),
            "weather_main": data['weather'][0]['main'],
            "weather_description": data['weather'][0]['description'],
            "visibility_meters": data.get('visibility', 0),
            "city_name": data.get('name', ''),
            "coordinates": {
                "latitude": data['coord']['lat'],
                "longitude": data['coord']['lon']
            },
            # Fire weather indicators
            "fire_weather_risk": self._calculate_fire_weather_risk(data)
        }
    
    def _parse_forecast_data(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse 5-day forecast data into standardized format"""
        forecast_items = []
        
        for item in data['list']:
            forecast_items.append({
                "timestamp": datetime.fromtimestamp(item['dt']).isoformat(),
                "temperature_celsius": item['main']['temp'],
                "humidity_percent": item['main']['humidity'],
                "pressure_hpa": item['main']['pressure'],
                "wind_speed_mps": item['wind'].get('speed', 0),
                "wind_direction_deg": item['wind'].get('deg', 0),
                "weather_main": item['weather'][0]['main'],
                "weather_description": item['weather'][0]['description'],
                "precipitation_mm": item.get('rain', {}).get('3h', 0) + item.get('snow', {}).get('3h', 0),
                "fire_weather_risk": self._calculate_fire_weather_risk(item)
            })
        
        return forecast_items
    
    def _calculate_fire_weather_risk(self, weather_data: Dict[str, Any]) -> str:
        """
        Calculate basic fire weather risk based on temperature, humidity, and wind
        
        This is a simplified example calculation - for production use, integrate with 
        National Fire Danger Rating System (NFDRS) or similar professional models
        """
        temp = weather_data['main']['temp']
        humidity = weather_data['main']['humidity']
        wind_speed = weather_data['wind'].get('speed', 0)
        
        # Basic fire weather risk assessment
        risk_score = 0
        
        # Temperature factor (higher temp = higher risk)
        if temp > 30:
            risk_score += 3
        elif temp > 25:
            risk_score += 2
        elif temp > 20:
            risk_score += 1
        
        # Humidity factor (lower humidity = higher risk)
        if humidity < 20:
            risk_score += 3
        elif humidity < 40:
            risk_score += 2
        elif humidity < 60:
            risk_score += 1
        
        # Wind factor (higher wind = higher risk)
        if wind_speed > 15:
            risk_score += 3
        elif wind_speed > 10:
            risk_score += 2
        elif wind_speed > 5:
            risk_score += 1
        
        # Classify risk level
        if risk_score >= 7:
            return "EXTREME"
        elif risk_score >= 5:
            return "HIGH"
        elif risk_score >= 3:
            return "MODERATE"
        else:
            return "LOW"