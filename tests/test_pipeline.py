#!/usr/bin/env python3
"""
Container Integration Tests

Comprehensive test suite for the containerized env-data-pipeline.
Tests container endpoints, data retrieval, and validation across all microservices.
"""

import sys
import os
import requests
import json
import time
import base64
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rasterio
import numpy as np
from io import BytesIO
# Metadata services now integrated into containers

# Container endpoints (use environment-specific endpoints)
import os

if os.getenv('PIPELINE_ENV') == 'production':
    ORCHESTRATOR_ENDPOINT = 'http://container-orchestrator:8000'
else:
    ORCHESTRATOR_ENDPOINT = 'http://localhost:8000'

# Orchestrator endpoints
DATA_COLLECTION_ENDPOINT = f"{ORCHESTRATOR_ENDPOINT}/collect"
CONTAINER_STATUS_ENDPOINT = f"{ORCHESTRATOR_ENDPOINT}/containers/status"
ORCHESTRATOR_HEALTH_ENDPOINT = f"{ORCHESTRATOR_ENDPOINT}/health"


def test_container_health():
    """Verify all containers are running and healthy through orchestrator."""
    try:
        # Check orchestrator health
        response = requests.get(ORCHESTRATOR_HEALTH_ENDPOINT, timeout=10)
        if response.status_code != 200:
            return False, {"orchestrator": False}
        
        # Check container status through orchestrator
        response = requests.get(CONTAINER_STATUS_ENDPOINT, timeout=15)
        if response.status_code == 200:
            status_data = response.json()
            container_status = status_data.get('container_status', {})
            
            # Convert status strings to boolean
            results = {}
            for service, status in container_status.items():
                results[service] = status == "healthy"
            
            return all(results.values()), results
        else:
            return False, {"status_check": False}
            
    except Exception as e:
        print(f"Health check failed: {e}")
        return False, {"exception": str(e)}


def test_container_data_retrieval():
    """Test data retrieval through orchestrator."""
    lat, lon = 34.0522, -118.2437  # Los Angeles test coordinates
    event_id = f"test_event_{int(time.time())}"
    
    payload = {
        "latitude": lat,
        "longitude": lon, 
        "event_id": event_id,
        "buffer_meters": 1000
    }
    
    try:
        response = requests.post(DATA_COLLECTION_ENDPOINT, json=payload, timeout=120)
        if response.status_code == 200:
            orchestrator_data = response.json()
            
            # Count successful services
            sources_success = 0
            total_errors = 0
            container_data = {}
            
            for service in ['landfire', 'modis', 'weather', 'topography']:
                if service in orchestrator_data and orchestrator_data[service]:
                    data = orchestrator_data[service]
                    container_data[service] = data
                    if data.get('raw_data') or data.get('interpreted_data'):
                        sources_success += 1
                    total_errors += len(data.get('errors', []))
                else:
                    total_errors += 1
            
            return container_data, sources_success, total_errors
        else:
            print(f"Orchestrator returned status {response.status_code}")
            return {}, 0, 1
            
    except Exception as e:
        print(f"Error calling orchestrator: {e}")
        return {}, 0, 1


def test_container_data_quality(container_data):
    """Validate container data quality and standardized format."""
    quality_checks = 0
    
    for service, data in container_data.items():
        # Check standardized schema format
        required_fields = ['source', 'data_type', 'location', 'timestamp', 'metadata']
        if all(field in data for field in required_fields):
            quality_checks += 1
        
        # Check metadata completeness
        if 'metadata' in data:
            metadata = data['metadata']
            if 'processing_time_ms' in metadata and 'quality_score' in metadata:
                quality_checks += 1
        
        # Check interpreted data exists
        if data.get('interpreted_data'):
            interpreted = data['interpreted_data']
            if 'coordinate_specific' in interpreted:
                quality_checks += 1
        
        # Service-specific validation
        if service == 'landfire' and data.get('raw_data'):
            # Check for binary data (base64 encoded)
            raw_data = data['raw_data']
            if any('data' in product for product in raw_data.values() if isinstance(product, dict)):
                quality_checks += 1
        
        elif service == 'modis' and data.get('interpreted_data'):
            # Check for vegetation indices
            coord_data = data['interpreted_data'].get('coordinate_specific', {})
            if 'ndvi_latest' in coord_data or 'vegetation_health' in coord_data:
                quality_checks += 1
    
    return quality_checks


def test_value_extraction(data):
    """Test pixel value extraction and validation."""
    validations_passed = 0
    
    # Test vegetation type extraction
    if 'landfire' in data and 'vegetation_type' in data['landfire']['data']:
        try:
            veg_data = data['landfire']['data']['vegetation_type']['data']
            with rasterio.open(BytesIO(veg_data)) as dataset:
                pixel_array = dataset.read(1)
                center_value = pixel_array[pixel_array.shape[0] // 2, pixel_array.shape[1] // 2]
                if center_value > 0:  # Valid vegetation code
                    validations_passed += 1
        except Exception:
            pass
    
    # Test elevation extraction
    if 'elevation' in data and data['elevation'].get('data'):
        try:
            elev_data = data['elevation']['data']
            with rasterio.open(BytesIO(elev_data)) as dataset:
                pixel_array = dataset.read(1)
                center_elevation = pixel_array[pixel_array.shape[0] // 2, pixel_array.shape[1] // 2]
                if 0 <= center_elevation <= 500:  # Reasonable elevation range
                    validations_passed += 1
        except Exception:
            pass
    
    # Test MODIS value extraction
    if 'modis' in data and 'MOD13Q1' in data['modis']['data']:
        mod13q1_data = data['modis']['data']['MOD13Q1']
        if mod13q1_data and len(mod13q1_data) > 0:
            try:
                latest_ndvi = mod13q1_data[-1].get('250m_16_days_NDVI', 0)
                if -1000 <= latest_ndvi <= 10000:  # Valid MODIS range
                    validations_passed += 1
            except (KeyError, IndexError):
                pass
    
    return validations_passed


def test_metadata_integration(data):
    """Test metadata extraction and S3 integration."""
    try:
        metadata = extract_all_metadata(data)
        extractor = LANDFIREMetadataExtractor()
        return metadata is not None
    except Exception:
        return False


def run_container_tests():
    """Execute complete container test suite."""
    print("Container Integration Test Suite")
    print("=" * 50)
    
    # Container health test
    print("1. Container Health Test")
    print("-" * 30)
    health_passed, health_results = test_container_health()
    for service, healthy in health_results.items():
        status = "✓" if healthy else "✗"
        print(f"{status} {service.capitalize()} container: {'healthy' if healthy else 'unhealthy'}")
    arch_passed = health_passed
    
    # Data retrieval test
    print("\n2. Container Data Retrieval Test")
    print("-" * 30)
    container_data, sources_success, total_errors = test_container_data_retrieval()
    print(f"✓ {sources_success}/4 containers operational")
    print(f"Total errors: {total_errors}")
    retrieval_passed = sources_success >= 3
    
    # Data quality test
    print("\n3. Container Data Quality Test")
    print("-" * 30)
    quality_score = test_container_data_quality(container_data)
    print(f"✓ {quality_score} containers passed quality validation")
    quality_passed = quality_score >= 6  # Higher threshold for container tests
    
    # Event coordination test
    print("\n4. Event ID Coordination Test")
    print("-" * 30)
    event_coordination_passed = test_event_coordination(container_data)
    if event_coordination_passed:
        print("✓ Event ID coordination working across containers")
    else:
        print("✗ Event ID coordination failed")
    
    # Final assessment
    all_tests = [arch_passed, retrieval_passed, quality_passed, event_coordination_passed]
    
    print("\n" + "=" * 50)
    print("CONTAINER TEST SUMMARY")
    
    if all(all_tests):
        print("✓ Container architecture functional")
        print("✓ Containers operational")
        print("✓ Standardized data format working")
        print("✓ Event coordination successful")
        print("\nSTATUS: CONTAINERIZED PIPELINE READY")
        return True
    else:
        print("✗ Some tests failed - containers require attention")
        return False


def test_event_coordination(container_data):
    """Test that all containers use the same event ID."""
    if not container_data:
        return False
    
    # Check if all containers returned data with the same event ID
    event_ids = set()
    for service, data in container_data.items():
        if 'event_id' in data and data['event_id']:
            event_ids.add(data['event_id'])
    
    # Should have exactly one unique event ID across all containers
    return len(event_ids) == 1


if __name__ == "__main__":
    success = run_container_tests()
    sys.exit(0 if success else 1)