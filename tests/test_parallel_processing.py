#!/usr/bin/env python3
"""
Parallel Processing Test for Environmental Data Pipeline

Tests the orchestrator's ability to handle multiple simultaneous requests
and demonstrates async parallel data collection across multiple geographic locations.
"""

import asyncio
import aiohttp
import time
import json
from datetime import datetime

# Test locations for parallel processing
TEST_LOCATIONS = {
    'los_angeles': {'lat': 34.0522, 'lon': -118.2437, 'name': 'Los Angeles, CA'},
    'yellowstone': {'lat': 44.6, 'lon': -110.5, 'name': 'Yellowstone, WY'}
}

# Orchestrator endpoint
ORCHESTRATOR_ENDPOINT = 'http://localhost:8000'
DATA_COLLECTION_ENDPOINT = f"{ORCHESTRATOR_ENDPOINT}/collect"


async def test_single_location(session: aiohttp.ClientSession, location_key: str, coords: dict):
    """Test data collection for a single location."""
    start_time = time.time()
    
    payload = {
        "latitude": coords['lat'],
        "longitude": coords['lon'],
        "event_id": f"parallel_test_{location_key}_{int(time.time())}",
        "buffer_meters": 1000
    }
    
    try:
        async with session.post(
            DATA_COLLECTION_ENDPOINT,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=120)
        ) as response:
            
            if response.status == 200:
                data = await response.json()
                processing_time = time.time() - start_time
                
                summary = data.get('summary', {})
                successful_sources = summary.get('successful_sources', 0)
                total_sources = summary.get('total_sources', 0)
                orchestrator_time = data.get('total_processing_time_ms', 0)
                
                return {
                    'location': location_key,
                    'name': coords['name'],
                    'success': successful_sources == total_sources,
                    'successful_sources': successful_sources,
                    'total_sources': total_sources,
                    'client_time_seconds': processing_time,
                    'orchestrator_time_ms': orchestrator_time,
                    'errors': summary.get('errors', [])
                }
            else:
                return {
                    'location': location_key,
                    'name': coords['name'],
                    'success': False,
                    'error': f"HTTP {response.status}"
                }
                
    except Exception as e:
        return {
            'location': location_key,
            'name': coords['name'],
            'success': False,
            'error': str(e)
        }


async def test_parallel_data_collection():
    """Test parallel data collection across multiple locations."""
    print("=" * 70)
    print("PARALLEL PROCESSING TEST - Environmental Data Pipeline")
    print("=" * 70)
    print(f"Testing {len(TEST_LOCATIONS)} locations simultaneously...")
    
    async with aiohttp.ClientSession() as session:
        # Create tasks for all locations
        tasks = []
        for location_key, coords in TEST_LOCATIONS.items():
            print(f"  Queuing: {coords['name']} ({coords['lat']}, {coords['lon']})")
            task = test_single_location(session, location_key, coords)
            tasks.append(task)
        
        print(f"\nStarting parallel execution at {datetime.now().strftime('%H:%M:%S')}...")
        start_time = time.time()
        
        # Execute all requests in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = time.time()
        total_parallel_time = end_time - start_time
        
        # Process and display results
        print(f"\nParallel execution completed in {total_parallel_time:.1f} seconds")
        print(f"Average time per location: {total_parallel_time/len(TEST_LOCATIONS):.1f} seconds")
        print("\n" + "=" * 70)
        print("RESULTS BY LOCATION")
        print("=" * 70)
        
        successful_locations = 0
        total_client_time = 0
        total_orchestrator_time = 0
        
        for result in results:
            if isinstance(result, Exception):
                print(f"ERROR Exception: {result}")
                continue
                
            location_name = result['name']
            if result['success']:
                successful_locations += 1
                total_client_time += result['client_time_seconds']
                total_orchestrator_time += result['orchestrator_time_ms']
                
                print(f"SUCCESS {location_name}")
                print(f"   Sources: {result['successful_sources']}/{result['total_sources']}")
                print(f"   Client time: {result['client_time_seconds']:.1f}s")
                print(f"   Orchestrator time: {result['orchestrator_time_ms']}ms")
            else:
                print(f"FAILED {location_name}")
                print(f"   Error: {result.get('error', 'Unknown error')}")
                if result.get('errors'):
                    for error in result['errors']:
                        print(f"   - {error}")
        
        # Performance analysis
        print("\n" + "=" * 70)
        print("PERFORMANCE ANALYSIS")
        print("=" * 70)
        
        success_rate = (successful_locations / len(TEST_LOCATIONS)) * 100
        avg_client_time = total_client_time / max(successful_locations, 1)
        avg_orchestrator_time = total_orchestrator_time / max(successful_locations, 1)
        
        # Calculate theoretical sequential time vs actual parallel time
        theoretical_sequential_time = avg_client_time * len(TEST_LOCATIONS)
        time_savings = theoretical_sequential_time - total_parallel_time
        efficiency = (time_savings / theoretical_sequential_time) * 100 if theoretical_sequential_time > 0 else 0
        
        print(f"Success Rate: {success_rate:.1f}% ({successful_locations}/{len(TEST_LOCATIONS)} locations)")
        print(f"Total Parallel Time: {total_parallel_time:.1f} seconds")
        print(f"Average Client Time: {avg_client_time:.1f} seconds per location")
        print(f"Average Orchestrator Time: {avg_orchestrator_time:.0f}ms per location")
        print(f"Theoretical Sequential Time: {theoretical_sequential_time:.1f} seconds")
        print(f"Time Savings: {time_savings:.1f} seconds ({efficiency:.1f}% efficiency gain)")
        
        # Determine overall result
        if success_rate == 100 and efficiency > 50:
            print(f"\nPARALLEL PROCESSING: EXCELLENT")
            print(f"   All locations succeeded with {efficiency:.1f}% efficiency gain")
            return True
        elif success_rate >= 75 and efficiency > 25:
            print(f"\nPARALLEL PROCESSING: GOOD")
            print(f"   Most locations succeeded with {efficiency:.1f}% efficiency gain")
            return True
        else:
            print(f"\nWARNING PARALLEL PROCESSING: NEEDS IMPROVEMENT")
            print(f"   Success rate: {success_rate:.1f}%, Efficiency: {efficiency:.1f}%")
            return False


def test_sequential_vs_parallel():
    """Compare sequential vs parallel processing performance."""
    print("\n" + "=" * 70)
    print("SEQUENTIAL VS PARALLEL COMPARISON")
    print("=" * 70)
    
    # This would be implemented to test sequential processing
    # For now, we'll just run the parallel test
    return asyncio.run(test_parallel_data_collection())


if __name__ == "__main__":
    print("Environmental Data Pipeline - Parallel Processing Test")
    print("Testing orchestrator's ability to handle concurrent requests...")
    
    try:
        success = test_sequential_vs_parallel()
        if success:
            print("\nPARALLEL PROCESSING TEST PASSED")
            print("Pipeline successfully handles concurrent requests with good performance")
        else:
            print("\nPARALLEL PROCESSING TEST FAILED")
            print("Pipeline needs optimization for concurrent request handling")
            
    except Exception as e:
        print(f"\n💥 TEST EXECUTION FAILED: {e}")
        success = False
    
    exit(0 if success else 1)