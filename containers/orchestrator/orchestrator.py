"""
Container Orchestrator Service

Coordinates data collection across multiple environmental data containers.
Implements event-driven architecture and aggregates responses using shared schema.
"""

import os
import asyncio
import aiohttp
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import json
import uuid

from shared_schema import AggregatedResponse, LocationInfo

app = FastAPI(title="Environmental Data Orchestrator", version="1.0.0")

# Container service endpoints
CONTAINER_ENDPOINTS = {
    "landfire": "http://landfire-container:8001",
    "modis": "http://modis-container:8002", 
    "weather": "http://weather-container:8003",
    "elevation": "http://elevation-container:8004"
}

class DataRequest(BaseModel):
    """Request model for environmental data collection"""
    latitude: float
    longitude: float
    buffer_meters: Optional[int] = 1000
    event_id: Optional[str] = None
    sources: Optional[List[str]] = None  # Specific sources to fetch, default: all

class EventUpdate(BaseModel):
    """Model for event-driven data updates"""
    event_id: str
    event_type: str  # "created", "updated", "location_changed"
    latitude: float
    longitude: float
    buffer_meters: Optional[int] = 1000
    priority: Optional[str] = "normal"  # "low", "normal", "high", "emergency"

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "orchestrator",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0"
    }

@app.post("/collect", response_model=dict)
async def collect_environmental_data(request: DataRequest):
    """
    Collect environmental data from all containers
    Coordinates parallel data collection and aggregates results
    """
    request_id = str(uuid.uuid4())
    start_time = datetime.now()
    
    # Determine which sources to fetch
    sources_to_fetch = request.sources or list(CONTAINER_ENDPOINTS.keys())
    
    # Create location info
    location = LocationInfo(
        latitude=request.latitude,
        longitude=request.longitude,
        buffer_meters=request.buffer_meters
    )
    
    # Parallel data collection from containers
    container_results = {}
    errors = []
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        
        for source in sources_to_fetch:
            if source in CONTAINER_ENDPOINTS:
                task = fetch_container_data(
                    session, 
                    source, 
                    CONTAINER_ENDPOINTS[source],
                    request
                )
                tasks.append((source, task))
        
        # Execute all container requests in parallel
        for source, task in tasks:
            try:
                result = await task
                container_results[source] = result
            except Exception as e:
                errors.append(f"Failed to fetch {source} data: {str(e)}")
                container_results[source] = None
    
    # Calculate processing time
    total_processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
    
    # Create aggregated response
    response = AggregatedResponse(
        request_id=request_id,
        event_id=request.event_id,
        location=location,
        timestamp=datetime.now().isoformat(),
        total_processing_time_ms=total_processing_time
    )
    
    # Assign container results
    if container_results.get("landfire"):
        response.landfire = container_results["landfire"]
    if container_results.get("modis"):
        response.modis = container_results["modis"]
    if container_results.get("weather"):
        response.weather = container_results["weather"]
    if container_results.get("elevation"):
        response.elevation = container_results["elevation"]
    
    # Create summary
    successful_sources = len([r for r in container_results.values() if r is not None])
    response.summary = {
        "total_sources": len(sources_to_fetch),
        "successful_sources": successful_sources,
        "total_errors": len(errors),
        "success_rate": successful_sources / len(sources_to_fetch) if sources_to_fetch else 0,
        "errors": errors
    }
    
    # Convert response to dict manually since container results are already dicts
    result = {
        "request_id": response.request_id,
        "event_id": response.event_id,
        "location": response.location.__dict__,
        "timestamp": response.timestamp,
        "summary": response.summary,
        "total_processing_time_ms": response.total_processing_time_ms
    }
    
    # Add container outputs (they're already dicts)
    if container_results.get("landfire"):
        result["landfire"] = container_results["landfire"]
    if container_results.get("modis"):
        result["modis"] = container_results["modis"]
    if container_results.get("weather"):
        result["weather"] = container_results["weather"]
    if container_results.get("elevation"):
        result["elevation"] = container_results["elevation"]
    
    return result

async def fetch_container_data(session: aiohttp.ClientSession, source: str, endpoint: str, request: DataRequest):
    """Fetch data from a specific container service"""
    
    # Prepare container-specific request
    container_request = {
        "latitude": request.latitude,
        "longitude": request.longitude,
        "event_id": request.event_id
    }
    
    # Add buffer_meters for applicable containers
    if source in ["landfire", "elevation"]:
        container_request["buffer_meters"] = request.buffer_meters
    
    try:
        # Make request to container
        async with session.post(
            f"{endpoint}/{source}",
            json=container_request,
            timeout=aiohttp.ClientTimeout(total=120)  # 2 minute timeout
        ) as response:
            
            if response.status == 200:
                return await response.json()
            else:
                error_text = await response.text()
                raise Exception(f"Container returned status {response.status}: {error_text}")
                
    except asyncio.TimeoutError:
        raise Exception(f"Container request timed out after 120 seconds")
    except aiohttp.ClientError as e:
        raise Exception(f"Network error: {str(e)}")

@app.post("/event-trigger")
async def handle_event_trigger(event: EventUpdate, background_tasks: BackgroundTasks):
    """
    Handle event-driven data collection
    Automatically triggered when events are created or updated
    """
    
    # Determine priority and sources based on event type
    if event.priority == "emergency":
        # Emergency events get all data sources immediately
        sources = list(CONTAINER_ENDPOINTS.keys())
        timeout = 60  # 1 minute for emergency
    elif event.event_type == "created":
        # New events get comprehensive data collection
        sources = list(CONTAINER_ENDPOINTS.keys())
        timeout = 120  # 2 minutes for complete collection
    else:
        # Updates might only need real-time data
        sources = ["weather"]  # Only update weather for minor updates
        timeout = 30  # 30 seconds for updates
    
    # Schedule background data collection
    background_tasks.add_task(
        collect_event_data,
        event.event_id,
        event.latitude,
        event.longitude,
        event.buffer_meters,
        sources,
        timeout
    )
    
    return {
        "status": "triggered",
        "event_id": event.event_id,
        "sources_scheduled": sources,
        "estimated_completion": timeout
    }

async def collect_event_data(event_id: str, latitude: float, longitude: float, 
                           buffer_meters: Optional[int], sources: List[str], timeout: int):
    """Background task for event-driven data collection"""
    
    try:
        # Create data request
        request = DataRequest(
            latitude=latitude,
            longitude=longitude,
            buffer_meters=buffer_meters,
            event_id=event_id,
            sources=sources
        )
        
        # Collect data (reuse existing collection logic)
        result = await collect_environmental_data(request)
        
        # TODO: Store result in database linked to event_id
        # TODO: Notify frontend via WebSocket of data availability
        # TODO: Trigger any post-processing workflows
        
        print(f"Event {event_id} data collection completed: {len(sources)} sources")
        
    except Exception as e:
        print(f"Event {event_id} data collection failed: {str(e)}")

@app.get("/containers/status")
async def get_container_status():
    """Check health status of all containers"""
    
    container_status = {}
    
    async with aiohttp.ClientSession() as session:
        for source, endpoint in CONTAINER_ENDPOINTS.items():
            try:
                async with session.get(f"{endpoint}/health", timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        container_status[source] = "healthy"
                    else:
                        container_status[source] = f"unhealthy (status: {response.status})"
            except Exception as e:
                container_status[source] = f"unreachable ({str(e)})"
    
    return {
        "orchestrator_status": "healthy",
        "container_status": container_status,
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")