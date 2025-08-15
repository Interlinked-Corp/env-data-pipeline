"""
Weather Container Service

Containerized microservice for weather data processing.
Implements the shared schema and provides REST API endpoints.
"""

import os
import sys
import asyncio
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

# Add parent directory to path to import services
sys.path.append('/app')
sys.path.append('/app/services')

from shared_schema import (
    ContainerOutput, LocationInfo, ProcessingMetadata, 
    InterpretedData, Sources, DataTypes
)

# Import the existing weather service
try:
    from services.weather_service import OpenWeatherMapService
except ImportError:
    # Fallback if service structure changes
    print("Warning: Could not import OpenWeatherMapService")
    OpenWeatherMapService = None

app = FastAPI(title="Weather Container Service", version="1.0.0")

# Initialize weather service
weather_service = OpenWeatherMapService() if OpenWeatherMapService else None

class WeatherRequest(BaseModel):
    """Request model for weather data"""
    latitude: float
    longitude: float
    event_id: Optional[str] = None

@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration"""
    return {
        "status": "healthy",
        "service": "weather-container",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

@app.post("/weather", response_model=dict)
async def get_weather_data(request: WeatherRequest):
    """
    Get weather data for specified coordinates
    Returns data in shared schema format
    """
    if not weather_service:
        raise HTTPException(status_code=503, detail="Weather service not available")
    
    start_time = datetime.now()
    
    try:
        # Get weather data using existing service
        weather_data = weather_service.get_data(request.latitude, request.longitude)
        
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        # Transform to shared schema format
        location = LocationInfo(
            latitude=request.latitude,
            longitude=request.longitude
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
            event_id=request.event_id,
            raw_data=weather_data,
            interpreted_data=interpreted_data,
            errors=weather_data.get("errors", [])
        )
        
        return container_output.to_dict()
        
    except Exception as e:
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        # Return error response in shared schema format
        error_output = ContainerOutput(
            source=Sources.OPENWEATHERMAP,
            data_type=DataTypes.WEATHER_CURRENT,
            location=LocationInfo(latitude=request.latitude, longitude=request.longitude),
            timestamp=datetime.now().isoformat(),
            metadata=ProcessingMetadata(
                processing_time_ms=processing_time,
                data_currency=datetime.now().isoformat(),
                retrieved_at=datetime.now().isoformat(),
                quality_score=0.0,
                container_id=f"weather-container-{os.getpid()}",
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
        "container": "weather-container",
        "version": "1.0.0",
        "schema_version": "1.0.0",
        "service_available": weather_service is not None,
        "api_key_configured": bool(os.getenv("OPENWEATHER_API_KEY")),
        "environment": os.getenv("OPENWEATHER_ENV", "unknown"),
        "endpoints": ["/health", "/weather", "/status"]
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8003))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")