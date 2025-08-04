"""
Metadata Integration Module

Provides unified metadata extraction across all data sources.
Coordinates between LANDFIRE and MODIS interpretation modules.
"""

from typing import Dict, Any
from .landfire_interpretation import extract_landfire_metadata
from .modis_interpretation import build_modis_scaling_table, apply_modis_scaling
import boto3
from config import aws_access_key_id, aws_secret_access_key, aws_region
from botocore.exceptions import ClientError

def connect_to_aws_s3() -> boto3.client:
    """
    Connect to AWS S3 using environment variables for credentials.

        
    Returns:
        boto3 S3 client
    """

    if not aws_access_key_id or not aws_secret_access_key:
        print("Error: AWS credentials not found in .env file")
        return None
    
    try:
        # Create S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=aws_region
        )
        return s3_client
    except ClientError as e:
        print(f"Error creating S3 client: {e}")
        return None


    s3_client = boto3.client('s3')
    return s3_client

def extract_all_metadata(pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract metadata from all data sources in pipeline output.
    
    Coordinates metadata extraction across LANDFIRE, MODIS, USGS, and Weather data.
    
    Args:
        pipeline_data: Complete pipeline output dictionary
        
    Returns:
        Dictionary containing metadata from all sources
    """
    metadata = {
        'extraction_timestamp': None,
        'sources': {}
    }
    
    # Extract LANDFIRE metadata
    try:
        landfire_metadata = extract_landfire_metadata(pipeline_data)
        if landfire_metadata:
            metadata['sources']['landfire'] = landfire_metadata.get('sources', {}).get('landfire', {})
            metadata['extraction_timestamp'] = landfire_metadata.get('extraction_timestamp')
    except Exception as e:
        metadata['sources']['landfire'] = {'error': f'LANDFIRE metadata extraction failed: {str(e)}'}
    
    # Extract MODIS metadata with scaling information
    try:
        if 'modis' in pipeline_data and pipeline_data['modis'].get('data'):
            modis_scaling = build_modis_scaling_table()
            metadata['sources']['modis'] = {
                'scaling_factors': modis_scaling,
                'products_available': list(pipeline_data['modis']['data'].keys()),
                'interpretation': 'Scaling factors available for value conversion'
            }
    except Exception as e:
        metadata['sources']['modis'] = {'error': f'MODIS metadata extraction failed: {str(e)}'}
    
    # Extract USGS metadata
    try:
        if 'elevation' in pipeline_data and pipeline_data['elevation'].get('data'):
            metadata['sources']['usgs'] = {
                'data_type': 'Digital Elevation Model',
                'units': 'meters',
                'interpretation': 'Elevation values in meters above sea level'
            }
    except Exception as e:
        metadata['sources']['usgs'] = {'error': f'USGS metadata extraction failed: {str(e)}'}
    
    # Extract Weather metadata
    try:
        if 'weather' in pipeline_data and pipeline_data['weather'].get('data'):
            metadata['sources']['weather'] = {
                'data_type': 'Current conditions and forecast',
                'units': {
                    'temperature': 'Celsius',
                    'wind_speed': 'm/s',
                    'humidity': 'percent',
                    'pressure': 'hPa'
                },
                'interpretation': 'Real-time weather data with fire risk assessment'
            }
    except Exception as e:
        metadata['sources']['weather'] = {'error': f'Weather metadata extraction failed: {str(e)}'}
    
    return metadata