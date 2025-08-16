"""
Input Validation Module

Validates input coordinates, parameters, and geographic coverage for the
Environmental Data Pipeline. Ensures data quality and prevents invalid requests.
"""

def validate_coordinates(lat: float, lon: float) -> dict:
    """
    Validate latitude and longitude coordinates.
    
    Args:
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees
        
    Returns:
        Dictionary with validation results and any errors
    """
    errors = []
    
    # Validate latitude range
    if not isinstance(lat, (int, float)):
        errors.append("Latitude must be a numeric value")
    elif not -90 <= lat <= 90:
        errors.append("Latitude must be between -90 and 90 degrees")
    
    # Validate longitude range
    if not isinstance(lon, (int, float)):
        errors.append("Longitude must be a numeric value")
    elif not -180 <= lon <= 180:
        errors.append("Longitude must be between -180 and 180 degrees")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "latitude": lat,
        "longitude": lon
    }


def validate_buffer_size(buffer_meters: int) -> dict:
    """
    Validate buffer size parameter.
    
    Args:
        buffer_meters: Buffer radius in meters
        
    Returns:
        Dictionary with validation results and any errors
    """
    errors = []
    
    # Validate buffer size type and range
    if not isinstance(buffer_meters, int):
        errors.append("Buffer size must be an integer")
    elif buffer_meters < 100:
        errors.append("Buffer size must be at least 100 meters")
    elif buffer_meters > 50000:
        errors.append("Buffer size must not exceed 50,000 meters")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "buffer_meters": buffer_meters
    }


def validate_geographic_coverage(lat: float, lon: float) -> dict:
    """
    Check if coordinates fall within supported geographic coverage.
    Currently supports Continental United States.
    
    Args:
        lat: Latitude in decimal degrees  
        lon: Longitude in decimal degrees
        
    Returns:
        Dictionary indicating coverage availability
    """
    # Continental United States bounds (approximate)
    conus_bounds = {
        "min_lat": 24.0,   # Southern Florida
        "max_lat": 49.0,   # Northern border
        "min_lon": -125.0, # West coast
        "max_lon": -66.0   # East coast
    }
    
    within_conus = (
        conus_bounds["min_lat"] <= lat <= conus_bounds["max_lat"] and
        conus_bounds["min_lon"] <= lon <= conus_bounds["max_lon"]
    )
    
    coverage_info = {
        "within_coverage": within_conus,
        "coverage_region": "Continental United States" if within_conus else "Outside coverage area",
        "latitude": lat,
        "longitude": lon
    }
    
    if not within_conus:
        coverage_info["warnings"] = [
            "Coordinates are outside Continental US coverage area",
            "Some data sources may not be available"
        ]
    
    return coverage_info