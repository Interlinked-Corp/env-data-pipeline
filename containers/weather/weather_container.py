"""
Weather Container Service

Containerized microservice for weather data processing.
Implements the shared schema and provides REST API endpoints.
"""

import os
import sys
import asyncio
import json
import requests
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import uvicorn

# Add parent directory to path to import shared modules
sys.path.append('/app')

from containers.shared_schema import (
    ContainerOutput, LocationInfo, ProcessingMetadata, 
    InterpretedData, Sources, DataTypes
)


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
        
        logger = logging.getLogger(__name__)
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
        logger = logging.getLogger(__name__)
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
            logger = logging.getLogger(__name__)
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
            logger = logging.getLogger(__name__)
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

# Structured logging configuration
class StructuredFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "service": "weather-container",
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        if hasattr(record, 'request_id'):
            log_entry["request_id"] = record.request_id
        if hasattr(record, 'event_id'):
            log_entry["event_id"] = record.event_id
        return json.dumps(log_entry)

# Configure structured logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
handler.setFormatter(StructuredFormatter())
logger.handlers = [handler]
logger.propagate = False

app = FastAPI(title="Weather Container Service", version="1.0.0")

def generate_request_id() -> str:
    """Generate unique request ID for tracing across systems"""
    import uuid
    return f"req_{uuid.uuid4().hex[:12]}"

def get_request_id_from_headers(request: Request) -> str:
    """Get or generate request ID for tracking"""
    request_id = request.headers.get("x-request-id") or request.headers.get("x-trace-id")
    if not request_id:
        request_id = generate_request_id()
    return request_id

# Initialize weather service
try:
    weather_service = OpenWeatherMapService()
    logger.info("Weather service initialized successfully")
except Exception as e:
    logger.error(f"Could not initialize weather service: {e}")
    weather_service = None

class WeatherRequest(BaseModel):
    """Request model for weather data"""
    latitude: float
    longitude: float
    event_id: Optional[str] = None

@app.get("/health")
async def health_check(request: Request):
    """Health check endpoint for container orchestration"""
    request_id = get_request_id_from_headers(request)
    
    logger.info(
        "Health check requested",
        extra={"request_id": request_id}
    )
    
    return {
        "status": "healthy",
        "service": "weather-container",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "request_id": request_id
    }

@app.post("/weather", response_model=dict)
async def get_weather_data(data_request: WeatherRequest, request: Request):
    """
    Get weather data for specified coordinates
    Returns data in shared schema format
    """
    if not weather_service:
        raise HTTPException(status_code=503, detail="Weather service not available")
    
    request_id = get_request_id_from_headers(request)
    start_time = datetime.now()
    
    logger.info(
        f"Weather data request started",
        extra={
            "request_id": request_id,
            "event_id": data_request.event_id,
            "latitude": data_request.latitude,
            "longitude": data_request.longitude
        }
    )
    
    try:
        # Get weather data using existing service
        weather_data = weather_service.get_data(data_request.latitude, data_request.longitude)
        
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        # Transform to shared schema format
        location = LocationInfo(
            latitude=data_request.latitude,
            longitude=data_request.longitude
        )
        
        metadata = ProcessingMetadata(
            processing_time_ms=processing_time,
            data_currency=datetime.now().isoformat(),
            retrieved_at=datetime.now().isoformat(),
            quality_score=1.0 if not weather_data.get("errors") else 0.8,
            container_id=f"weather-container-{os.getpid()}",
            container_version="1.0.0"
        )
        
        # Extract interpreted data from weather service response
        interpreted_data = None
        if weather_data.get("data"):
            current = weather_data["data"].get("current", {})
            forecast = weather_data["data"].get("forecast", [])
            
            interpreted_data = InterpretedData(
                coordinate_specific={
                    "temperature_celsius": current.get("temperature_celsius"),
                    "humidity_percent": current.get("humidity_percent"),
                    "wind_speed_mps": current.get("wind_speed_mps"),
                    "fire_weather_risk": current.get("fire_weather_risk"),
                    "weather_main": current.get("weather_main"),
                    "weather_description": current.get("weather_description")
                },
                area_summary={
                    "current_conditions": current,
                    "forecast_summary": {
                        "total_points": len(forecast),
                        "max_temperature": max([f.get("temperature_celsius", 0) for f in forecast]) if forecast else None,
                        "min_temperature": min([f.get("temperature_celsius", 0) for f in forecast]) if forecast else None,
                        "fire_risk_periods": [f for f in forecast if f.get("fire_weather_risk") in ["HIGH", "EXTREME"]]
                    }
                },
                risk_assessment=current.get("fire_weather_risk", "UNKNOWN")
            )
        
        # Create standardized container output
        container_output = ContainerOutput(
            source=Sources.OPENWEATHERMAP,
            data_type=DataTypes.WEATHER_CURRENT,
            location=location,
            timestamp=datetime.now().isoformat(),
            metadata=metadata,
            event_id=data_request.event_id,
            raw_data=weather_data,
            interpreted_data=interpreted_data,
            errors=weather_data.get("errors", [])
        )
        
        # Log successful completion with performance metrics
        logger.info(
            f"Weather data collection completed successfully",
            extra={
                "request_id": request_id,
                "event_id": data_request.event_id,
                "duration_ms": processing_time,
                "has_interpreted_data": interpreted_data is not None,
                "error_count": len(container_output.errors or [])
            }
        )
        
        response_dict = container_output.to_dict()
        response_dict["request_id"] = request_id
        return response_dict
        
    except Exception as e:
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        # Log error with context
        logger.error(
            f"Weather data collection failed: {str(e)}",
            extra={
                "request_id": request_id,
                "event_id": data_request.event_id,
                "duration_ms": processing_time,
                "error": str(e)
            }
        )
        
        # Return error response in shared schema format
        error_output = ContainerOutput(
            source=Sources.OPENWEATHERMAP,
            data_type=DataTypes.WEATHER_CURRENT,
            location=LocationInfo(latitude=data_request.latitude, longitude=data_request.longitude),
            timestamp=datetime.now().isoformat(),
            metadata=ProcessingMetadata(
                processing_time_ms=processing_time,
                data_currency=datetime.now().isoformat(),
                retrieved_at=datetime.now().isoformat(),
                quality_score=0.0,
                container_id=f"weather-container-{os.getpid()}",
                container_version="1.0.0"
            ),
            event_id=data_request.event_id,
            errors=[str(e)]
        )
        
        error_response = error_output.to_dict()
        error_response["request_id"] = request_id
        return error_response

@app.get("/status")
async def get_status(request: Request):
    """Get container status and configuration"""
    request_id = get_request_id_from_headers(request)
    
    logger.info(
        "Status check requested",
        extra={"request_id": request_id}
    )
    return {
        "container": "weather-container",
        "version": "1.0.0",
        "schema_version": "1.0.0",
        "service_available": weather_service is not None,
        "api_key_configured": bool(os.getenv("OPENWEATHER_API_KEY")),
        "environment": os.getenv("OPENWEATHER_ENV", "unknown"),
        "endpoints": ["/health", "/weather", "/status"],
        "request_id": request_id
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8003))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")