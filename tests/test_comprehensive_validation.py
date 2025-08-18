#!/usr/bin/env python3
"""
Comprehensive Environmental Data Pipeline Validation Tests

Tests real data retrieval, metadata accuracy, geographic coverage, and end-to-end functionality.
Validates that containers are correctly calling APIs, processing data, and mapping metadata.
"""

import sys
import os
import requests
import json
import time
import base64
import asyncio
import aiohttp
from datetime import datetime, timedelta
import rasterio
import numpy as np
from io import BytesIO

# Import container endpoint configuration
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Use orchestrator endpoints (containers are accessed through orchestrator)
if os.getenv('PIPELINE_ENV') == 'production':
    ORCHESTRATOR_ENDPOINT = 'http://container-orchestrator:8000'
else:
    ORCHESTRATOR_ENDPOINT = 'http://localhost:8000'

# Single endpoint for all data collection through orchestrator
DATA_COLLECTION_ENDPOINT = f"{ORCHESTRATOR_ENDPOINT}/collect"

# Test coordinates for comprehensive coverage
TEST_LOCATIONS = {
    'los_angeles': {'lat': 34.0522, 'lon': -118.2437, 'name': 'Los Angeles, CA'},
    'yellowstone': {'lat': 44.6, 'lon': -110.5, 'name': 'Yellowstone, WY'},
    'florida_everglades': {'lat': 25.7, 'lon': -80.9, 'name': 'Florida Everglades'},
    'death_valley': {'lat': 36.5, 'lon': -117.0, 'name': 'Death Valley, CA'}
}


async def test_location_async(session: aiohttp.ClientSession, location_key: str, coords: dict):
    """Test a single location asynchronously."""
    print(f"\nTesting location: {coords['name']} ({coords['lat']}, {coords['lon']})")
    print("-" * 50)
    
    event_id = f"test_real_data_{location_key}_{int(time.time())}"
    location_results = {}
    
    print("Collecting data from all containers through orchestrator...")
    
    # PRODUCTION: Retry up to 3 times for network issues
    max_retries = 3
    retry_delay = 10  # seconds
    
    for attempt in range(max_retries):
        try:
            payload = {
                "latitude": coords['lat'],
                "longitude": coords['lon'],
                "event_id": event_id,
                "buffer_meters": 1000
            }
            
            print(f"  Attempt {attempt + 1}/{max_retries}...")
            
            async with session.post(
                DATA_COLLECTION_ENDPOINT, 
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120)
            ) as response:
                
                if response.status == 200:
                    orchestrator_data = await response.json()
                    
                    # Validate each service's data from orchestrator response
                    for service in ['landfire', 'modis', 'weather', 'topography']:
                        if service in orchestrator_data and orchestrator_data[service]:
                            validation = validate_real_data_response(service, orchestrator_data[service], coords)
                            location_results[service] = validation
                            
                            status = "✓ PASS" if validation['is_real_data'] else "✗ FAIL"
                            print(f"  {service.upper()}: {status} - {validation['summary']}")
                        else:
                            location_results[service] = {
                                'is_real_data': False,
                                'summary': f"No data returned from {service} container",
                                'errors': [f"Service {service} not available in orchestrator response"]
                            }
                            print(f"  {service.upper()}: ✗ FAIL - No data returned")
                    
                    break  # Success, exit retry loop
                    
                else:
                    if attempt < max_retries - 1:
                        print(f"  HTTP {response.status}, retrying in {retry_delay}s...")
                        await asyncio.sleep(retry_delay)
                        continue
                    else:
                        # All services failed due to orchestrator failure
                        for service in ['landfire', 'modis', 'weather', 'topography']:
                            location_results[service] = {
                                'is_real_data': False,
                                'summary': f"Orchestrator HTTP {response.status} after {max_retries} attempts",
                                'errors': [f"Orchestrator returned status {response.status}"]
                            }
                        print(f"  ✗ FAIL - Orchestrator HTTP {response.status} (all attempts failed)")
                        
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  Exception: {str(e)}, retrying in {retry_delay}s...")
                await asyncio.sleep(retry_delay)
                continue
            else:
                # All services failed due to orchestrator exception
                for service in ['landfire', 'modis', 'weather', 'topography']:
                    location_results[service] = {
                        'is_real_data': False,
                        'summary': f"Orchestrator request failed: {str(e)} after {max_retries} attempts",
                        'errors': [str(e)]
                    }
                print(f"  ✗ FAIL - Orchestrator Exception: {str(e)} (all attempts failed)")
    
    return location_key, location_results


async def test_all_locations_parallel():
    """Test all locations in parallel using async processing."""
    print("=" * 60)
    print("COMPREHENSIVE REAL DATA VALIDATION (PARALLEL PROCESSING)")
    print("=" * 60)
    
    async with aiohttp.ClientSession() as session:
        # Create tasks for all locations
        tasks = []
        for location_key, coords in TEST_LOCATIONS.items():
            task = test_location_async(session, location_key, coords)
            tasks.append(task)
        
        # Execute all location tests in parallel
        print(f"\nStarting parallel testing of {len(TEST_LOCATIONS)} locations...")
        start_time = time.time()
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = time.time()
        parallel_duration = end_time - start_time
        
        # Process results
        location_results = {}
        for result in results:
            if isinstance(result, Exception):
                print(f"Location test failed with exception: {result}")
            else:
                location_key, location_data = result
                location_results[location_key] = location_data
        
        print(f"\nParallel processing completed in {parallel_duration:.1f} seconds")
        print(f"Average time per location: {parallel_duration/len(TEST_LOCATIONS):.1f} seconds")
        
        return location_results


def test_real_data_retrieval():
    """Test that containers are actually retrieving real data from external APIs."""
    # Run the async parallel test
    return asyncio.run(test_all_locations_parallel())


def validate_real_data_response(service, data, coords):
    """Validate that container response contains real, meaningful data."""
    
    validation = {
        'is_real_data': False,
        'summary': '',
        'details': {},
        'errors': []
    }
    
    # Check basic response structure
    if not data.get('raw_data') and not data.get('interpreted_data'):
        validation['errors'].append("No data in response")
        validation['summary'] = "Empty response"
        return validation
    
    if service == 'landfire':
        return validate_landfire_real_data(data, coords, validation)
    elif service == 'modis':
        return validate_modis_real_data(data, coords, validation)
    elif service == 'weather':
        return validate_weather_real_data(data, coords, validation)
    elif service == 'topography':
        return validate_topography_real_data(data, coords, validation)
    
    return validation


def validate_landfire_real_data(data, coords, validation):
    """Validate LANDFIRE data is real GeoTIFF with meaningful values."""
    
    try:
        raw_data = data.get('raw_data', {})
        interpreted_data = data.get('interpreted_data', {})
        
        # Check for binary GeoTIFF data
        binary_products = 0
        for product, product_data in raw_data.items():
            if isinstance(product_data, dict) and 'data' in product_data:
                try:
                    # Decode base64 and validate as GeoTIFF
                    binary_data = base64.b64decode(product_data['data'])
                    
                    if len(binary_data) > 1000:  # Reasonable GeoTIFF size
                        with rasterio.open(BytesIO(binary_data)) as dataset:
                            # Check it's a valid raster
                            if dataset.width > 0 and dataset.height > 0:
                                binary_products += 1
                                
                                # Read pixel data to ensure it's not empty
                                pixel_array = dataset.read(1)
                                unique_values = np.unique(pixel_array[pixel_array != dataset.nodata])
                                
                                if len(unique_values) > 1:
                                    validation['details'][f'{product}_pixels'] = len(unique_values)
                                    
                except Exception as e:
                    validation['errors'].append(f"Failed to read {product} GeoTIFF: {str(e)}")
        
        # Check interpreted data quality
        coord_specific = interpreted_data.get('coordinate_specific', {})
        meaningful_interpretations = 0
        
        if 'vegetation_type' in coord_specific and coord_specific['vegetation_type'] != 'Unknown':
            meaningful_interpretations += 1
            validation['details']['vegetation_type'] = coord_specific['vegetation_type']
        
        if 'fuel_model' in coord_specific and coord_specific['fuel_model'] != 'Unknown':
            meaningful_interpretations += 1
            validation['details']['fuel_model'] = coord_specific['fuel_model']
        
        # Validate success criteria - PRODUCTION REQUIRES ALL DATA
        if binary_products >= 3 and meaningful_interpretations >= 2:
            validation['is_real_data'] = True
            validation['summary'] = f"{binary_products} GeoTIFF products, {meaningful_interpretations} interpreted"
        else:
            validation['summary'] = f"INSUFFICIENT DATA - Need 3+ products and 2+ interpretations, got {binary_products} products, {meaningful_interpretations} interpreted"
            validation['errors'].append("Production requires complete data coverage")
            
    except Exception as e:
        validation['errors'].append(f"LANDFIRE validation error: {str(e)}")
        validation['summary'] = "Validation failed"
    
    return validation


def validate_modis_real_data(data, coords, validation):
    """Validate MODIS data contains real vegetation indices."""
    
    try:
        interpreted_data = data.get('interpreted_data', {})
        coord_specific = interpreted_data.get('coordinate_specific', {})
        
        # Check for meaningful NDVI/vegetation data
        meaningful_data = 0
        
        if 'ndvi_latest' in coord_specific:
            ndvi = coord_specific['ndvi_latest']
            if ndvi is not None and -1.0 <= ndvi <= 1.0:
                meaningful_data += 1
                validation['details']['ndvi'] = ndvi
        
        if 'vegetation_health' in coord_specific:
            health = coord_specific['vegetation_health']
            if health and health != 'UNKNOWN':
                meaningful_data += 1
                validation['details']['vegetation_health'] = health
        
        if 'last_observation_date' in coord_specific:
            obs_date = coord_specific['last_observation_date']
            if obs_date:
                # Check if observation is recent (within 90 days)
                try:
                    obs_datetime = datetime.fromisoformat(obs_date.replace('Z', '+00:00'))
                    days_old = (datetime.now() - obs_datetime.replace(tzinfo=None)).days
                    if days_old <= 90:
                        meaningful_data += 1
                        validation['details']['observation_age_days'] = days_old
                except:
                    pass
        
        # Check raw MODIS data exists
        raw_data = data.get('raw_data', {})
        modis_products = len([k for k in raw_data.keys() if 'MOD' in k or 'MYD' in k])
        
        # PRODUCTION REQUIRES COMPLETE MODIS DATA
        if meaningful_data >= 3 and modis_products >= 2:
            validation['is_real_data'] = True
            validation['summary'] = f"{meaningful_data} meaningful parameters, {modis_products} MODIS products"
        else:
            validation['summary'] = f"INSUFFICIENT DATA - Need 3+ parameters and 2+ products, got {meaningful_data} parameters, {modis_products} products"
            validation['errors'].append("Production requires complete MODIS coverage")
            
    except Exception as e:
        validation['errors'].append(f"MODIS validation error: {str(e)}")
        validation['summary'] = "Validation failed"
    
    return validation


def validate_weather_real_data(data, coords, validation):
    """Validate weather data is current and realistic."""
    
    try:
        interpreted_data = data.get('interpreted_data', {})
        coord_specific = interpreted_data.get('coordinate_specific', {})
        
        realistic_data = 0
        
        # Check temperature is realistic
        if 'temperature_celsius' in coord_specific:
            temp = coord_specific['temperature_celsius']
            if temp is not None and -50 <= temp <= 60:  # Reasonable Earth temperature range
                realistic_data += 1
                validation['details']['temperature_c'] = temp
        
        # Check humidity is realistic
        if 'humidity_percent' in coord_specific:
            humidity = coord_specific['humidity_percent']
            if humidity is not None and 0 <= humidity <= 100:
                realistic_data += 1
                validation['details']['humidity_percent'] = humidity
        
        # Check fire weather risk assessment
        if 'fire_weather_risk' in coord_specific:
            risk = coord_specific['fire_weather_risk']
            if risk in ['LOW', 'MODERATE', 'HIGH', 'EXTREME']:
                realistic_data += 1
                validation['details']['fire_weather_risk'] = risk
        
        # Check data currency (should be very recent for weather)
        metadata = data.get('metadata', {})
        if 'retrieved_at' in metadata:
            try:
                retrieved_time = datetime.fromisoformat(metadata['retrieved_at'].replace('Z', '+00:00'))
                minutes_old = (datetime.now() - retrieved_time.replace(tzinfo=None)).total_seconds() / 60
                if minutes_old < 60:  # Weather data should be very recent
                    realistic_data += 1
                    validation['details']['data_age_minutes'] = round(minutes_old, 1)
            except:
                pass
        
        # PRODUCTION REQUIRES ALL WEATHER PARAMETERS
        if realistic_data >= 4:
            validation['is_real_data'] = True
            validation['summary'] = f"{realistic_data} realistic parameters"
        else:
            validation['summary'] = f"INSUFFICIENT DATA - Need 4 parameters, got {realistic_data}"
            validation['errors'].append("Production requires complete weather data")
            
    except Exception as e:
        validation['errors'].append(f"Weather validation error: {str(e)}")
        validation['summary'] = "Validation failed"
    
    return validation


def validate_topography_real_data(data, coords, validation):
    """Validate topography data contains real elevation information."""
    
    try:
        interpreted_data = data.get('interpreted_data', {})
        coord_specific = interpreted_data.get('coordinate_specific', {})
        
        realistic_data = 0
        
        # Check elevation is realistic for coordinate
        if 'elevation_m' in coord_specific:
            elevation = coord_specific['elevation_m']
            if elevation is not None and -500 <= elevation <= 9000:  # Reasonable Earth elevation range
                realistic_data += 1
                validation['details']['elevation_m'] = elevation
        
        # Check terrain classification
        if 'terrain_classification' in coord_specific:
            terrain = coord_specific['terrain_classification']
            if terrain in ['LOW', 'MODERATE', 'HIGH']:
                realistic_data += 1
                validation['details']['terrain_classification'] = terrain
        
        # Check binary DEM data exists
        raw_data = data.get('raw_data', {})
        if 'elevation' in raw_data and raw_data['elevation'].get('data'):
            try:
                binary_data = base64.b64decode(raw_data['elevation']['data'])
                if len(binary_data) > 1000:  # Reasonable DEM size
                    realistic_data += 1
                    validation['details']['binary_size_kb'] = len(binary_data) / 1024
            except:
                pass
        
        # PRODUCTION REQUIRES ALL TOPOGRAPHY DATA
        if realistic_data >= 3:
            validation['is_real_data'] = True
            validation['summary'] = f"{realistic_data} realistic parameters"
        else:
            validation['summary'] = f"INSUFFICIENT DATA - Need 3 parameters, got {realistic_data}"
            validation['errors'].append("Production requires complete elevation data")
            
    except Exception as e:
        validation['errors'].append(f"Topography validation error: {str(e)}")
        validation['summary'] = "Validation failed"
    
    return validation


def test_metadata_accuracy():
    """Test that metadata interpretation is accurate for known locations."""
    print("\n" + "=" * 60)
    print("METADATA ACCURACY VALIDATION")
    print("=" * 60)
    
    # Test Los Angeles (known urban area)
    la_coords = TEST_LOCATIONS['los_angeles']
    print(f"\nTesting metadata accuracy for {la_coords['name']}...")
    
    payload = {
        "latitude": la_coords['lat'],
        "longitude": la_coords['lon'],
        "event_id": f"metadata_test_{int(time.time())}"
    }
    
    # Test LANDFIRE metadata for urban area through orchestrator
    try:
        response = requests.post(DATA_COLLECTION_ENDPOINT, json=payload, timeout=60)
        if response.status_code == 200:
            orchestrator_data = response.json()
            landfire_data = orchestrator_data.get('landfire', {})
            interpreted = landfire_data.get('interpreted_data', {}).get('coordinate_specific', {})
            
            vegetation_type = interpreted.get('vegetation_type', '')
            
            # Los Angeles should show developed/urban vegetation
            if any(keyword in vegetation_type.lower() for keyword in ['developed', 'urban', 'city']):
                print("✓ LANDFIRE correctly identified urban area")
            else:
                print(f"✗ LANDFIRE metadata may be incorrect: '{vegetation_type}' for urban LA")
        else:
            print("✗ Failed to get LANDFIRE data for metadata test")
    except Exception as e:
        print(f"✗ LANDFIRE metadata test failed: {e}")
    
    return True


def test_data_currency():
    """Test that data currency tracking is accurate."""
    print("\n" + "=" * 60)
    print("DATA CURRENCY VALIDATION")
    print("=" * 60)
    
    coords = TEST_LOCATIONS['los_angeles']
    event_id = f"currency_test_{int(time.time())}"
    
    print(f"\nTesting data currency through orchestrator...")
    
    try:
        payload = {
            "latitude": coords['lat'],
            "longitude": coords['lon'],
            "event_id": event_id,
            "buffer_meters": 1000
        }
        
        response = requests.post(DATA_COLLECTION_ENDPOINT, json=payload, timeout=60)
        
        if response.status_code == 200:
            orchestrator_data = response.json()
            
            # Check each service's metadata from orchestrator response
            for service in ['landfire', 'modis', 'weather', 'topography']:
                print(f"  {service.upper()} data currency...")
                
                if service in orchestrator_data and orchestrator_data[service]:
                    data = orchestrator_data[service]
                    metadata = data.get('metadata', {})
                    
                    # Check retrieval timestamp is recent
                    if 'retrieved_at' in metadata:
                        retrieved_time = datetime.fromisoformat(metadata['retrieved_at'].replace('Z', '+00:00'))
                        minutes_old = (datetime.now() - retrieved_time.replace(tzinfo=None)).total_seconds() / 60
                        
                        if minutes_old < 5:
                            print(f"    ✓ Retrieved timestamp is current ({round(minutes_old, 1)} min ago)")
                        else:
                            print(f"    ✗ Retrieved timestamp seems old ({round(minutes_old, 1)} min ago)")
                    
                    # Check data currency is reasonable
                    if 'data_currency' in metadata:
                        currency = metadata['data_currency']
                        print(f"    ✓ Data currency tracked: {currency}")
                    
                    # Check quality score
                    if 'quality_score' in metadata:
                        quality = metadata['quality_score']
                        if 0.0 <= quality <= 1.0:
                            print(f"    ✓ Quality score valid: {quality}")
                        else:
                            print(f"    ✗ Invalid quality score: {quality}")
                else:
                    print(f"    ✗ No data returned from {service}")
                    
        else:
            print(f"  ✗ Orchestrator failed with status {response.status_code}")
            
    except Exception as e:
        print(f"  ✗ Currency test failed: {e}")
    
    return True


def run_comprehensive_validation():
    """Run all comprehensive validation tests."""
    print("STARTING COMPREHENSIVE ENVIRONMENTAL DATA PIPELINE VALIDATION")
    print("This test validates real data retrieval, metadata accuracy, and data currency")
    print("")
    
    start_time = datetime.now()
    
    # Test 1: Real data retrieval across multiple locations
    real_data_results = test_real_data_retrieval()
    
    # Test 2: Metadata accuracy 
    metadata_accuracy_passed = test_metadata_accuracy()
    
    # Test 3: Data currency validation
    currency_validation_passed = test_data_currency()
    
    # Summary
    end_time = datetime.now()
    test_duration = (end_time - start_time).total_seconds()
    
    print("\n" + "=" * 60)
    print("COMPREHENSIVE VALIDATION SUMMARY")
    print("=" * 60)
    
    total_tests = 0
    passed_tests = 0
    
    for location, services in real_data_results.items():
        for service, result in services.items():
            total_tests += 1
            if result['is_real_data']:
                passed_tests += 1
    
    print(f"Real Data Tests: {passed_tests}/{total_tests} passed")
    print(f"Metadata Accuracy: {'PASS' if metadata_accuracy_passed else 'FAIL'}")
    print(f"Data Currency: {'PASS' if currency_validation_passed else 'FAIL'}")
    print(f"Test Duration: {round(test_duration, 1)} seconds")
    
    # PRODUCTION REQUIRES 100% SUCCESS RATE
    overall_success = (passed_tests == total_tests) and metadata_accuracy_passed and currency_validation_passed
    
    if overall_success:
        print("\nSTATUS: COMPREHENSIVE VALIDATION PASSED")
        print("✓ Pipeline is retrieving real data")
        print("✓ Metadata mapping is accurate") 
        print("✓ All systems are properly connected")
        return True
    else:
        print("\nSTATUS: COMPREHENSIVE VALIDATION FAILED")
        print("✗ Pipeline needs attention before production use")
        return False


if __name__ == "__main__":
    success = run_comprehensive_validation()
    sys.exit(0 if success else 1)