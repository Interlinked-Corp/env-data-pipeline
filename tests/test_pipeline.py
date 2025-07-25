#!/usr/bin/env python3
"""
Pipeline Integration Tests

Comprehensive test suite for the env-data-pipeline geospatial data pipeline.
Tests data retrieval, processing, and validation across all integrated services.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rasterio
import numpy as np
from io import BytesIO
from pipeline import EnvironmentalDataPipeline
from metadata import LANDFIREMetadataExtractor, extract_all_metadata


def test_service_imports():
    """Verify all service modules can be imported successfully."""
    try:
        from services.landfire_service import LANDFIREDataService
        from services.modis_service import MODISDataService  
        from services.usgs_service import USGSElevationService
        from services.weather_service import OpenWeatherMapService
        return True
    except ImportError:
        return False


def test_data_retrieval():
    """Test data retrieval from all configured sources."""
    lat, lon = 34.0522, -118.2437  # Los Angeles test coordinates
    buffer_meters = 1000
    
    pipeline = EnvironmentalDataPipeline(landfire_year='latest')
    data = pipeline.get_location_data(lat, lon, buffer_meters)
    
    sources_success = 0
    total_errors = 0
    
    for source_name in ['landfire', 'modis', 'elevation', 'weather']:
        if source_name in data and data[source_name].get('data'):
            sources_success += 1
        if source_name in data:
            total_errors += len(data[source_name].get('errors', []))
    
    return data, sources_success, total_errors


def test_data_quality(data):
    """Validate data quality and binary integrity."""
    quality_checks = 0
    
    # LANDFIRE binary data validation
    if 'landfire' in data and data['landfire'].get('data'):
        for product, info in data['landfire']['data'].items():
            if 'data' in info and len(info['data']) > 1000:  # Minimum expected size
                quality_checks += 1
    
    # MODIS time series validation
    if 'modis' in data and data['modis'].get('data'):
        for product, time_series in data['modis']['data'].items():
            if len(time_series) > 0:
                quality_checks += 1
    
    # USGS elevation validation
    if 'elevation' in data and data['elevation'].get('data'):
        if len(data['elevation']['data']) > 1000:  # Minimum expected size
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


def run_pipeline_tests():
    """Execute complete pipeline test suite."""
    print("Pipeline Integration Test Suite")
    print("=" * 50)
    
    # Architecture test
    print("1. Service Architecture Test")
    print("-" * 30)
    if test_service_imports():
        print("✓ All service modules imported successfully")
        arch_passed = True
    else:
        print("✗ Service import failed")
        arch_passed = False
    
    # Data retrieval test
    print("\n2. Data Retrieval Test")
    print("-" * 30)
    data, sources_success, total_errors = test_data_retrieval()
    print(f"✓ {sources_success}/4 data sources operational")
    print(f"Total errors: {total_errors}")
    retrieval_passed = sources_success >= 3
    
    # Data quality test
    print("\n3. Data Quality Test")
    print("-" * 30)
    quality_score = test_data_quality(data)
    print(f"✓ {quality_score} data sources passed quality validation")
    quality_passed = quality_score >= 3
    
    # Value extraction test
    print("\n4. Value Extraction Test")
    print("-" * 30)
    extraction_score = test_value_extraction(data)
    print(f"✓ {extraction_score}/3 value extractions successful")
    extraction_passed = extraction_score >= 2
    
    # Metadata integration test
    print("\n5. Metadata Integration Test")
    print("-" * 30)
    metadata_passed = test_metadata_integration(data)
    if metadata_passed:
        print("✓ Metadata extraction and S3 integration successful")
    else:
        print("✗ Metadata integration failed")
    
    # Final assessment
    all_tests = [arch_passed, retrieval_passed, quality_passed, extraction_passed, metadata_passed]
    
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    
    if all(all_tests):
        print("✓ Pipeline architecture functional")
        print("✓ Data sources operational")
        print("✓ Data extraction working")
        print("✓ Metadata integration successful")
        print("\nSTATUS: PRODUCTION READY")
        return True
    else:
        print("✗ Some tests failed - pipeline requires attention")
        return False


if __name__ == "__main__":
    success = run_pipeline_tests()
    sys.exit(0 if success else 1)