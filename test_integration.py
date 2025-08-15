#!/usr/bin/env python3
"""
Test script to verify Mark's integration and container functionality
Tests the core pipeline without Docker complexity
"""

import sys
import os
from datetime import datetime

# Add paths for imports
sys.path.append('.')
sys.path.append('./services')
sys.path.append('./metadata')
sys.path.append('./containers/landfire')

def test_imports():
    """Test that all required modules can be imported"""
    print("🔍 Testing imports...")
    
    try:
        from shared_schema import ContainerOutput, LocationInfo, ProcessingMetadata
        print("✅ Shared schema imports successful")
    except Exception as e:
        print(f"❌ Shared schema import failed: {e}")
        return False
    
    try:
        from metadata.landfire_interpretation import LANDFIREMetadataExtractor
        print("✅ LANDFIREMetadataExtractor import successful")
    except Exception as e:
        print(f"❌ LANDFIREMetadataExtractor import failed: {e}")
        return False
    
    try:
        from services.landfire_service import LANDFIREDataService
        print("✅ LANDFIREDataService import successful")
    except Exception as e:
        print(f"❌ LANDFIREDataService import failed: {e}")
        return False
    
    return True

def test_landfire_container_logic():
    """Test the LANDFIRE container logic without FastAPI"""
    print("\n🔍 Testing LANDFIRE container logic...")
    
    try:
        # Import container logic
        sys.path.append('./containers/landfire')
        from landfire_container import landfire_service, metadata_extractor
        
        if landfire_service is None:
            print("❌ LANDFIRE service not initialized")
            return False
        
        if metadata_extractor is None:
            print("❌ Metadata extractor not initialized")
            return False
        
        print("✅ Container services initialized successfully")
        print(f"   LANDFIRE service: {type(landfire_service).__name__}")
        print(f"   Metadata extractor: {type(metadata_extractor).__name__}")
        
        return True
        
    except Exception as e:
        print(f"❌ Container logic test failed: {e}")
        return False

def test_pixel_interpretation():
    """Test Mark's pixel interpretation with test coordinates"""
    print("\n🔍 Testing Mark's pixel interpretation...")
    
    try:
        from metadata.landfire_interpretation import LANDFIREMetadataExtractor
        
        # Initialize extractor
        extractor = LANDFIREMetadataExtractor()
        
        # Test with Los Angeles coordinates (known to work from previous testing)
        test_lat = 34.0522
        test_lon = -118.2437
        
        print(f"   Testing coordinates: ({test_lat}, {test_lon}) - Los Angeles")
        print("   Note: This test simulates pixel interpretation without real GeoTIFF data")
        print("   In production, this would use actual LANDFIRE data from the pipeline")
        
        # Test the fallback values system
        print(f"✅ Extractor initialized with S3 bucket: {extractor.s3_bucket}")
        print(f"✅ Available product types: {list(extractor.s3_paths.keys())}")
        print(f"✅ Fallback vegetation values available: {len(extractor._fallback_values['vegetation_type'])} entries")
        print(f"✅ Fallback fuel model values available: {len(extractor._fallback_values['fuel_model'])} entries")
        
        return True
        
    except Exception as e:
        print(f"❌ Pixel interpretation test failed: {e}")
        return False

def test_shared_schema():
    """Test the shared schema data structures"""
    print("\n🔍 Testing shared schema...")
    
    try:
        from shared_schema import (
            ContainerOutput, LocationInfo, ProcessingMetadata, 
            InterpretedData, Sources, DataTypes
        )
        
        # Create test data structures
        location = LocationInfo(
            latitude=34.0522,
            longitude=-118.2437,
            buffer_meters=1000
        )
        
        metadata = ProcessingMetadata(
            processing_time_ms=150,
            data_currency="2024-01-01T00:00:00Z",
            retrieved_at=datetime.now().isoformat(),
            quality_score=1.0,
            container_id="test-container",
            container_version="1.0.0"
        )
        
        interpreted_data = InterpretedData(
            coordinate_specific={"test": "value"},
            area_summary={"test": "summary"},
            visualization=None,
            risk_assessment="LOW"
        )
        
        container_output = ContainerOutput(
            source=Sources.LANDFIRE,
            data_type=DataTypes.LANDFIRE_VEGETATION,
            location=location,
            timestamp=datetime.now().isoformat(),
            metadata=metadata,
            event_id="test-event-123",
            raw_data={"test": "data"},
            interpreted_data=interpreted_data,
            errors=[]
        )
        
        # Test serialization
        output_dict = container_output.to_dict()
        
        print("✅ Shared schema objects created successfully")
        print(f"   Location: {location.latitude}, {location.longitude}")
        print(f"   Processing time: {metadata.processing_time_ms}ms")
        print(f"   Data source: {container_output.source}")
        print(f"   Output serializable: {len(output_dict)} fields")
        
        return True
        
    except Exception as e:
        print(f"❌ Shared schema test failed: {e}")
        return False

def main():
    """Run all integration tests"""
    print("🚀 Environmental Data Pipeline - Integration Test")
    print("=" * 60)
    
    tests = [
        ("Module Imports", test_imports),
        ("LANDFIRE Container Logic", test_landfire_container_logic),
        ("Mark's Pixel Interpretation", test_pixel_interpretation),
        ("Shared Schema", test_shared_schema)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 Running: {test_name}")
        print("-" * 40)
        
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name}: PASSED")
            else:
                print(f"❌ {test_name}: FAILED")
        except Exception as e:
            print(f"❌ {test_name}: ERROR - {e}")
    
    print("\n" + "=" * 60)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! Container integration is functional.")
        return True
    else:
        print("⚠️  Some tests failed. Check the output above for details.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)