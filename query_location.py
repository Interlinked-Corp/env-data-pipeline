#!/usr/bin/env python3
"""
Query specific coordinates with the environmental data pipeline
"""

import sys
import json
from pipeline import EnvironmentalDataPipeline

def query_location(lat, lon, buffer_meters=1000):
    """Query pipeline for specific coordinates"""
    print(f"Querying environmental data for ({lat}, {lon}) with {buffer_meters}m buffer...")
    print("=" * 70)
    
    # Initialize pipeline
    pipeline = EnvironmentalDataPipeline(landfire_year='latest')
    
    # Get data
    data = pipeline.get_location_data(lat, lon, buffer_meters)
    
    # Print summary
    print(f"\nResults for ({lat}, {lon}):")
    print(f"  LANDFIRE data: {len(data['landfire'].get('data', {}))} products")
    print(f"  MODIS data: {len(data['modis'].get('data', {}))} product types") 
    print(f"  Elevation data: {'Available' if data['elevation'].get('data') else 'Not available'}")
    print(f"  Weather data: {'Available' if data['weather'].get('data') else 'Not available'}")
    print(f"  Total errors: {data['summary']['total_errors']}")
    print(f"  Timeliness score: {data['summary']['timeliness_score']}/100")
    
    # Show current weather if available
    if data['weather'].get('data', {}).get('current'):
        weather = data['weather']['data']['current']
        print(f"\nCurrent Weather:")
        print(f"  Temperature: {weather['temperature_celsius']}°C")
        print(f"  Humidity: {weather['humidity_percent']}%")
        print(f"  Wind: {weather['wind_speed_mps']} m/s")
        print(f"  Fire Weather Risk: {weather['fire_weather_risk']}")
    
    return data

if __name__ == "__main__":
    # Default coordinates (Los Angeles)
    lat = 34.0522
    lon = -118.2437
    buffer_meters = 1000
    
    # Check for command line arguments
    if len(sys.argv) >= 3:
        lat = float(sys.argv[1])
        lon = float(sys.argv[2])
    if len(sys.argv) >= 4:
        buffer_meters = int(sys.argv[3])
    
    # Query the location
    result = query_location(lat, lon, buffer_meters)
    
    # Optionally save to JSON file
    if len(sys.argv) >= 5 and sys.argv[4] == "--save":
        filename = f"environmental_data_{lat}_{lon}.json"
        with open(filename, 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\nData saved to: {filename}")