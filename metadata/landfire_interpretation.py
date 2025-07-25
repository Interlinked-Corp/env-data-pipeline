#!/usr/bin/env python3
"""
Metadata Extraction and Value Interpretation Script

Extracts and interprets metadata from geospatial data products:
- LANDFIRE: Decodes categorical pixel values using attribute tables
- MODIS: Interprets vegetation indices and biophysical parameters
- USGS 3DEP: Processes elevation data and derivatives
- Weather: Structures current and forecast data

This script provides methods to convert raw binary data into meaningful
information using official metadata sources and value interpretation tables.
"""

import json
import csv
import requests
import rasterio
import numpy as np
import boto3
from io import BytesIO, StringIO
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class LANDFIREMetadataExtractor:
    """
    LANDFIRE metadata extraction and pixel value interpretation
    
    Uses official LANDFIRE CSV attribute tables to decode categorical
    pixel values from GeoTIFF raster data into meaningful categories.
    """
    
    def __init__(self, s3_bucket: str = "env-data-prod", s3_region: str = "us-east-2"):
        """Initialize LANDFIRE metadata extractor with S3 configuration."""
        
        # S3 configuration for accessing pre-processed LANDFIRE files
        self.s3_bucket = s3_bucket
        self.s3_region = s3_region
        self.s3_client = boto3.client('s3', region_name=s3_region)
        
        # S3 paths to LANDFIRE attribute tables and data files
        self.s3_paths = {
            'vegetation_type': 'raw/landfire/evt/unzipped/',
            'fuel_model': 'raw/landfire/fm40/unzipped/',
            'canopy_cover': 'raw/landfire/cc/unzipped/',
            'canopy_height': 'raw/landfire/ch/unzipped/',
            'canopy_bulk_density': 'raw/landfire/cbd/unzipped/',
            'canopy_base_height': 'raw/landfire/cbh/unzipped/',
            'slope': 'raw/landfire/slpp/unzipped/',
            'aspect': 'raw/landfire/asp/unzipped/',
            'elevation': 'raw/landfire/elev/unzipped/'
        }
        
        # Cache for downloaded attribute tables
        self._attribute_cache = {}
        
        # Fallback lookup tables for critical values
        self._fallback_values = {
            'vegetation_type': {
                7113: 'Urban-Low Intensity',
                7118: 'Urban-Medium Intensity', 
                7296: 'California Coastal Scrub',
                7297: 'Developed-Open Space',
                7298: 'Developed-Low Intensity',
                7299: 'Developed-Medium Intensity'
            },
            'fuel_model': {
                91: 'Urban/Developed (Non-burnable)',
                92: 'Snow/Ice (Non-burnable)',
                93: 'Agriculture (Non-burnable)',
                98: 'Water (Non-burnable)',
                99: 'Barren (Non-burnable)',
                101: 'Short Grass (1 hr)',
                102: 'Timber (Grass and Understory)',
                103: 'Tall Grass (1 hr)',
                104: 'Chaparral (6 ft)'
            }
        }
    
    def extract_raster_metadata(self, geotiff_bytes: bytes, product_type: str) -> Dict[str, Any]:
        """
        Extract metadata and pixel statistics from GeoTIFF binary data
        
        Args:
            geotiff_bytes: Raw GeoTIFF binary data
            product_type: LANDFIRE product type (e.g., 'vegetation_type')
            
        Returns:
            Dictionary containing raster metadata and pixel statistics
        """
        try:
            with rasterio.open(BytesIO(geotiff_bytes)) as dataset:
                # Basic raster properties
                metadata = {
                    'product_type': product_type,
                    'width': dataset.width,
                    'height': dataset.height,
                    'count': dataset.count,
                    'dtype': str(dataset.dtypes[0]),
                    'crs': str(dataset.crs),
                    'transform': list(dataset.transform),
                    'bounds': list(dataset.bounds),
                    'nodata': dataset.nodata
                }
                
                # Read pixel data
                pixel_data = dataset.read(1)
                
                # Calculate pixel statistics
                valid_pixels = pixel_data[pixel_data != dataset.nodata] if dataset.nodata else pixel_data
                metadata['pixel_stats'] = {
                    'min': float(np.min(valid_pixels)),
                    'max': float(np.max(valid_pixels)),
                    'mean': float(np.mean(valid_pixels)),
                    'std': float(np.std(valid_pixels)),
                    'unique_values': len(np.unique(valid_pixels)),
                    'total_pixels': pixel_data.size,
                    'valid_pixels': len(valid_pixels)
                }
                
                # Add value interpretation
                metadata['value_interpretation'] = self._interpret_pixel_values(
                    valid_pixels, product_type
                )
                
                return metadata
                
        except Exception as e:
            logger.error(f"Error extracting raster metadata: {e}")
            return {'error': str(e)}
    
    def _interpret_pixel_values(self, pixel_values: np.ndarray, product_type: str) -> Dict[str, Any]:
        """Interpret pixel values using attribute tables or known ranges."""
        
        interpretation = {'type': 'unknown'}
        
        # Categorical products with attribute tables
        if product_type in ['vegetation_type', 'fuel_model']:
            interpretation = self._decode_categorical_values(pixel_values, product_type)
            
        # Continuous products with known ranges
        elif product_type == 'canopy_cover':
            interpretation = {
                'type': 'continuous',
                'unit': 'percent',
                'range': '0-100',
                'description': 'Percentage of ground covered by tree canopy'
            }
        elif product_type in ['canopy_height', 'canopy_base_height']:
            interpretation = {
                'type': 'continuous', 
                'unit': 'meters',
                'range': '0-50+',
                'description': f'Tree {product_type.replace("_", " ")} in meters'
            }
        elif product_type == 'canopy_bulk_density':
            interpretation = {
                'type': 'continuous',
                'unit': 'kg/m³',
                'range': '0-255 (scaled)',
                'description': 'Density of canopy fuels'
            }
        elif product_type == 'slope':
            interpretation = {
                'type': 'continuous',
                'unit': 'degrees', 
                'range': '0-90',
                'description': 'Slope steepness in degrees'
            }
        elif product_type == 'aspect':
            interpretation = {
                'type': 'continuous',
                'unit': 'degrees',
                'range': '0-360',
                'description': 'Slope direction (0=North, 90=East, 180=South, 270=West)'
            }
        elif product_type == 'elevation':
            interpretation = {
                'type': 'continuous',
                'unit': 'meters',
                'range': 'varies by location',
                'description': 'Ground elevation above sea level'
            }
            
        return interpretation
    
    def _decode_categorical_values(self, pixel_values: np.ndarray, product_type: str) -> Dict[str, Any]:
        """Decode categorical pixel values using S3-stored LANDFIRE attribute tables."""
        
        try:
            # Try to get attribute table from S3 cache
            if product_type not in self._attribute_cache:
                value_map = self._load_attribute_table_from_s3(product_type)
                if value_map:
                    self._attribute_cache[product_type] = value_map
                else:
                    # Use fallback values if S3 lookup fails
                    logger.warning(f"Using fallback values for {product_type}")
                    self._attribute_cache[product_type] = self._fallback_values.get(product_type, {})
            
            # Get unique values and their meanings
            unique_values = np.unique(pixel_values)
            value_map = self._attribute_cache[product_type]
            
            decoded_values = {}
            for value in unique_values:
                decoded_values[int(value)] = value_map.get(int(value), f'Unknown ({value})')
            
            return {
                'type': 'categorical',
                'unique_count': len(unique_values),
                'decoded_values': decoded_values,
                'coverage_summary': self._calculate_coverage(pixel_values, decoded_values),
                'data_source': 'S3' if product_type in self._attribute_cache else 'fallback'
            }
            
        except Exception as e:
            logger.error(f"Error decoding categorical values: {e}")
            return {'type': 'categorical', 'error': str(e)}
    
    def _load_attribute_table_from_s3(self, product_type: str) -> Optional[Dict[int, str]]:
        """Load LANDFIRE attribute table from S3 bucket."""
        
        s3_prefix = self.s3_paths.get(product_type)
        if not s3_prefix:
            return None
        
        try:
            # List CSV files in the S3 prefix
            response = self.s3_client.list_objects_v2(
                Bucket=self.s3_bucket,
                Prefix=s3_prefix,
                MaxKeys=50
            )
            
            csv_file = None
            for obj in response.get('Contents', []):
                if obj['Key'].endswith('.csv'):
                    csv_file = obj['Key']
                    break
            
            if not csv_file:
                logger.warning(f"No CSV attribute table found in {s3_prefix}")
                return None
            
            # Download and parse CSV from S3
            logger.info(f"Loading attribute table from s3://{self.s3_bucket}/{csv_file}")
            response = self.s3_client.get_object(Bucket=self.s3_bucket, Key=csv_file)
            csv_content = response['Body'].read().decode('utf-8')
            
            # Parse CSV data
            csv_data = StringIO(csv_content)
            reader = csv.DictReader(csv_data)
            
            # Build value lookup dictionary
            value_map = {}
            for row in reader:
                try:
                    value = int(row['VALUE'])
                    if product_type == 'vegetation_type':
                        label = row.get('EVT_NAME', row.get('CLASSNAME', 'Unknown'))
                    elif product_type == 'fuel_model':
                        label = row.get('FBFM40_DESC', row.get('CLASSNAME', 'Unknown'))
                    else:
                        label = row.get('CLASSNAME', f'Class {value}')
                    
                    value_map[value] = label
                except (ValueError, KeyError):
                    continue
            
            logger.info(f"Loaded {len(value_map)} attribute mappings for {product_type}")
            return value_map
            
        except Exception as e:
            logger.error(f"Error loading attribute table from S3: {e}")
            return None
    
    def _calculate_coverage(self, pixel_values: np.ndarray, decoded_values: Dict[int, str]) -> Dict[str, float]:
        """Calculate percentage coverage for each category."""
        
        unique, counts = np.unique(pixel_values, return_counts=True)
        total_pixels = len(pixel_values)
        
        coverage = {}
        for value, count in zip(unique, counts):
            label = decoded_values.get(int(value), f'Unknown ({value})')
            percentage = (count / total_pixels) * 100
            coverage[label] = round(percentage, 2)
        
        return coverage


class MODISMetadataExtractor:
    """
    MODIS metadata extraction and value interpretation
    
    Interprets MODIS vegetation indices, biophysical parameters,
    and provides quality assessment information.
    """
    
    def __init__(self):
        """Initialize MODIS metadata extractor with product specifications."""
        
        # MODIS product specifications
        self.product_specs = {
            'MOD13Q1': {
                'description': 'Terra Vegetation Indices 16-Day 250m',
                'temporal_resolution': '16 days',
                'spatial_resolution': '250m',
                'parameters': {
                    'NDVI': {'range': '(-1, 1)', 'scale': 0.0001, 'description': 'Normalized Difference Vegetation Index'},
                    'EVI': {'range': '(-1, 1)', 'scale': 0.0001, 'description': 'Enhanced Vegetation Index'},
                    'VI_Quality': {'type': 'bitmask', 'description': 'Vegetation Index Quality flags'},
                    'red_reflectance': {'range': '(0, 1)', 'scale': 0.0001, 'description': 'Red surface reflectance'},
                    'nir_reflectance': {'range': '(0, 1)', 'scale': 0.0001, 'description': 'NIR surface reflectance'},
                    'blue_reflectance': {'range': '(0, 1)', 'scale': 0.0001, 'description': 'Blue surface reflectance'},
                    'mir_reflectance': {'range': '(0, 1)', 'scale': 0.0001, 'description': 'MIR surface reflectance'}
                }
            },
            'MYD13Q1': {
                'description': 'Aqua Vegetation Indices 16-Day 250m', 
                'temporal_resolution': '16 days',
                'spatial_resolution': '250m',
                'parameters': {
                    'NDVI': {'range': '(-1, 1)', 'scale': 0.0001, 'description': 'Normalized Difference Vegetation Index'},
                    'EVI': {'range': '(-1, 1)', 'scale': 0.0001, 'description': 'Enhanced Vegetation Index'},
                    'VI_Quality': {'type': 'bitmask', 'description': 'Vegetation Index Quality flags'}
                }
            },
            'MOD15A2H': {
                'description': 'Terra Leaf Area Index/FPAR 8-Day 500m',
                'temporal_resolution': '8 days', 
                'spatial_resolution': '500m',
                'parameters': {
                    'Lai_500m': {'range': '(0, 10)', 'scale': 0.1, 'description': 'Leaf Area Index'},
                    'Fpar_500m': {'range': '(0, 1)', 'scale': 0.01, 'description': 'Fraction of Photosynthetically Active Radiation'}
                }
            },
            'MYD15A2H': {
                'description': 'Aqua Leaf Area Index/FPAR 8-Day 500m',
                'temporal_resolution': '8 days',
                'spatial_resolution': '500m', 
                'parameters': {
                    'Lai_500m': {'range': '(0, 10)', 'scale': 0.1, 'description': 'Leaf Area Index'},
                    'Fpar_500m': {'range': '(0, 1)', 'scale': 0.01, 'description': 'Fraction of Photosynthetically Active Radiation'}
                }
            },
            'MOD11A2': {
                'description': 'Terra Land Surface Temperature 8-Day 1km',
                'temporal_resolution': '8 days',
                'spatial_resolution': '1km',
                'parameters': {
                    'LST_Day_1km': {'range': '(7500, 65535)', 'scale': 0.02, 'offset': -273.15, 'description': 'Daytime Land Surface Temperature (Kelvin)'},
                    'LST_Night_1km': {'range': '(7500, 65535)', 'scale': 0.02, 'offset': -273.15, 'description': 'Nighttime Land Surface Temperature (Kelvin)'}
                }
            },
            'MYD11A2': {
                'description': 'Aqua Land Surface Temperature 8-Day 1km',
                'temporal_resolution': '8 days', 
                'spatial_resolution': '1km',
                'parameters': {
                    'LST_Day_1km': {'range': '(7500, 65535)', 'scale': 0.02, 'offset': -273.15, 'description': 'Daytime Land Surface Temperature (Kelvin)'},
                    'LST_Night_1km': {'range': '(7500, 65535)', 'scale': 0.02, 'offset': -273.15, 'description': 'Nighttime Land Surface Temperature (Kelvin)'}
                }
            },
            'MOD17A2H': {
                'description': 'Terra Gross Primary Productivity 8-Day 500m',
                'temporal_resolution': '8 days',
                'spatial_resolution': '500m',
                'parameters': {
                    'Gpp_500m': {'range': '(0, 30000)', 'scale': 0.0001, 'description': 'Gross Primary Productivity (kg C/m²)'}
                }
            },
            'MYD17A2H': {
                'description': 'Aqua Gross Primary Productivity 8-Day 500m', 
                'temporal_resolution': '8 days',
                'spatial_resolution': '500m',
                'parameters': {
                    'Gpp_500m': {'range': '(0, 30000)', 'scale': 0.0001, 'description': 'Gross Primary Productivity (kg C/m²)'}
                }
            }
        }
    
    def extract_time_series_metadata(self, modis_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract metadata from MODIS time series data
        
        Args:
            modis_data: Raw MODIS data from ORNL API
            
        Returns:
            Dictionary containing time series metadata and interpreted values
        """
        metadata = {
            'source': 'MODIS_ORNL',
            'extraction_time': datetime.now().isoformat(),
            'products': {}
        }
        
        for product_name, product_data in modis_data.get('data', {}).items():
            if 'data' in product_data and 'subset' in product_data['data']:
                metadata['products'][product_name] = self._analyze_product_time_series(
                    product_name, product_data['data']['subset']
                )
        
        return metadata
    
    def _analyze_product_time_series(self, product_name: str, time_series: List[Dict]) -> Dict[str, Any]:
        """Analyze individual MODIS product time series."""
        
        if not time_series:
            return {'error': 'No time series data available'}
        
        product_spec = self.product_specs.get(product_name, {})
        
        analysis = {
            'product_info': product_spec,
            'temporal_coverage': {
                'start_date': time_series[0].get('calendar_date'),
                'end_date': time_series[-1].get('calendar_date'),
                'data_points': len(time_series)
            },
            'data_quality': self._assess_data_quality(time_series),
            'parameter_statistics': {}
        }
        
        # Analyze each parameter in the time series
        if time_series and 'data' in time_series[0]:
            sample_data = time_series[0]['data']
            if isinstance(sample_data, list) and sample_data:
                # ORNL returns data as lists - need to interpret based on product type
                analysis['parameter_statistics'] = self._calculate_parameter_stats(
                    time_series, product_name
                )
        
        return analysis
    
    def _assess_data_quality(self, time_series: List[Dict]) -> Dict[str, Any]:
        """Assess data quality metrics for time series."""
        
        total_points = len(time_series)
        valid_points = 0
        missing_points = 0
        
        for point in time_series:
            if 'data' in point and point['data']:
                valid_points += 1
            else:
                missing_points += 1
        
        return {
            'total_points': total_points,
            'valid_points': valid_points, 
            'missing_points': missing_points,
            'completeness_percent': round((valid_points / total_points) * 100, 2) if total_points > 0 else 0,
            'temporal_gaps': self._identify_temporal_gaps(time_series)
        }
    
    def _identify_temporal_gaps(self, time_series: List[Dict]) -> List[str]:
        """Identify significant temporal gaps in the time series."""
        
        gaps = []
        dates = [point.get('calendar_date') for point in time_series if point.get('calendar_date')]
        
        if len(dates) < 2:
            return gaps
        
        # Convert to datetime objects for gap analysis
        try:
            date_objects = [datetime.strptime(date, '%Y-%m-%d') for date in dates]
            date_objects.sort()
            
            for i in range(1, len(date_objects)):
                gap_days = (date_objects[i] - date_objects[i-1]).days
                if gap_days > 20:  # Significant gap for most MODIS products
                    gaps.append(f"Gap of {gap_days} days between {date_objects[i-1].strftime('%Y-%m-%d')} and {date_objects[i].strftime('%Y-%m-%d')}")
        
        except ValueError as e:
            logger.warning(f"Error parsing dates for gap analysis: {e}")
        
        return gaps
    
    def _calculate_parameter_stats(self, time_series: List[Dict], product_name: str) -> Dict[str, Any]:
        """Calculate statistics for MODIS parameters over time."""
        
        # ORNL API returns data as lists - extract values based on known MODIS structure
        if product_name in ['MOD13Q1', 'MYD13Q1']:
            return self._analyze_vegetation_indices(time_series)
        elif product_name in ['MOD15A2H', 'MYD15A2H']:
            return self._analyze_lai_fpar(time_series)
        elif product_name in ['MOD11A2', 'MYD11A2']:
            return self._analyze_land_surface_temperature(time_series)
        elif product_name in ['MOD17A2H', 'MYD17A2H']:
            return self._analyze_gpp(time_series)
        else:
            return {'error': f'Unknown product type: {product_name}'}
    
    def _analyze_vegetation_indices(self, time_series: List[Dict]) -> Dict[str, Any]:
        """Analyze NDVI/EVI vegetation indices."""
        
        # MODIS vegetation indices are typically scaled integers
        # ORNL API may return them as processed values or raw values
        values = []
        for point in time_series:
            if 'data' in point and isinstance(point['data'], list) and point['data']:
                # Take first two values as NDVI and EVI (typical MODIS structure)
                values.append(point['data'][:2])
        
        if not values:
            return {'error': 'No valid vegetation index data'}
        
        values_array = np.array(values)
        
        return {
            'NDVI': {
                'min': float(np.min(values_array[:, 0])) if values_array.shape[1] > 0 else None,
                'max': float(np.max(values_array[:, 0])) if values_array.shape[1] > 0 else None,
                'mean': float(np.mean(values_array[:, 0])) if values_array.shape[1] > 0 else None,
                'std': float(np.std(values_array[:, 0])) if values_array.shape[1] > 0 else None
            },
            'EVI': {
                'min': float(np.min(values_array[:, 1])) if values_array.shape[1] > 1 else None,
                'max': float(np.max(values_array[:, 1])) if values_array.shape[1] > 1 else None,
                'mean': float(np.mean(values_array[:, 1])) if values_array.shape[1] > 1 else None,
                'std': float(np.std(values_array[:, 1])) if values_array.shape[1] > 1 else None
            }
        }
    
    def _analyze_lai_fpar(self, time_series: List[Dict]) -> Dict[str, Any]:
        """Analyze Leaf Area Index and FPAR."""
        
        # Extract LAI and FPAR values
        lai_values = []
        fpar_values = []
        
        for point in time_series:
            if 'data' in point and isinstance(point['data'], list) and len(point['data']) >= 2:
                lai_values.append(point['data'][0])  # LAI typically first
                fpar_values.append(point['data'][1])  # FPAR typically second
        
        return {
            'LAI': self._calculate_stats(lai_values) if lai_values else None,
            'FPAR': self._calculate_stats(fpar_values) if fpar_values else None
        }
    
    def _analyze_land_surface_temperature(self, time_series: List[Dict]) -> Dict[str, Any]:
        """Analyze Land Surface Temperature."""
        
        day_temps = []
        night_temps = []
        
        for point in time_series:
            if 'data' in point and isinstance(point['data'], list) and len(point['data']) >= 2:
                day_temps.append(point['data'][0])  # Day LST
                night_temps.append(point['data'][1])  # Night LST
        
        return {
            'Day_LST': self._calculate_stats(day_temps) if day_temps else None,
            'Night_LST': self._calculate_stats(night_temps) if night_temps else None
        }
    
    def _analyze_gpp(self, time_series: List[Dict]) -> Dict[str, Any]:
        """Analyze Gross Primary Productivity."""
        
        gpp_values = []
        for point in time_series:
            if 'data' in point and isinstance(point['data'], list) and point['data']:
                gpp_values.append(point['data'][0])  # GPP value
        
        return {
            'GPP': self._calculate_stats(gpp_values) if gpp_values else None
        }
    
    def _calculate_stats(self, values: List[float]) -> Dict[str, float]:
        """Calculate basic statistics for a list of values."""
        
        if not values:
            return None
        
        values_array = np.array(values)
        return {
            'min': float(np.min(values_array)),
            'max': float(np.max(values_array)),
            'mean': float(np.mean(values_array)),
            'std': float(np.std(values_array)),
            'count': len(values)
        }


class USGSElevationMetadataExtractor:
    """
    USGS 3DEP elevation metadata extraction and interpretation
    
    Processes elevation data and calculates terrain derivatives.
    """
    
    def __init__(self):
        """Initialize USGS elevation metadata extractor."""
        self.vertical_datum = 'NAVD88'
        self.horizontal_datum = 'NAD83' 
        self.unit = 'meters'
    
    def extract_elevation_metadata(self, geotiff_bytes: bytes) -> Dict[str, Any]:
        """
        Extract metadata from USGS elevation GeoTIFF
        
        Args:
            geotiff_bytes: Raw elevation GeoTIFF binary data
            
        Returns:
            Dictionary containing elevation metadata and terrain analysis
        """
        try:
            with rasterio.open(BytesIO(geotiff_bytes)) as dataset:
                # Read elevation data
                elevation_data = dataset.read(1)
                
                # Basic metadata
                metadata = {
                    'source': 'USGS_3DEP',
                    'vertical_datum': self.vertical_datum,
                    'horizontal_datum': self.horizontal_datum,
                    'unit': self.unit,
                    'width': dataset.width,
                    'height': dataset.height,
                    'crs': str(dataset.crs),
                    'transform': list(dataset.transform),
                    'bounds': list(dataset.bounds),
                    'nodata': dataset.nodata
                }
                
                # Calculate elevation statistics
                valid_elevations = elevation_data[elevation_data != dataset.nodata] if dataset.nodata else elevation_data
                
                metadata['elevation_stats'] = {
                    'min_elevation': float(np.min(valid_elevations)),
                    'max_elevation': float(np.max(valid_elevations)),
                    'mean_elevation': float(np.mean(valid_elevations)),
                    'elevation_range': float(np.max(valid_elevations) - np.min(valid_elevations)),
                    'std_elevation': float(np.std(valid_elevations))
                }
                
                # Calculate terrain derivatives
                metadata['terrain_analysis'] = self._calculate_terrain_derivatives(
                    elevation_data, dataset.transform, dataset.nodata
                )
                
                return metadata
                
        except Exception as e:
            logger.error(f"Error extracting elevation metadata: {e}")
            return {'error': str(e)}
    
    def _calculate_terrain_derivatives(self, elevation_data: np.ndarray, 
                                     transform: Any, nodata: Optional[float]) -> Dict[str, Any]:
        """Calculate slope, aspect, and other terrain derivatives."""
        
        try:
            # Get pixel size from transform
            pixel_size = abs(transform[0])  # Assumes square pixels
            
            # Calculate gradients
            dy, dx = np.gradient(elevation_data, pixel_size)
            
            # Calculate slope in degrees
            slope = np.degrees(np.arctan(np.sqrt(dx**2 + dy**2)))
            
            # Calculate aspect in degrees (0-360, where 0 is North)
            aspect = np.degrees(np.arctan2(-dx, dy))
            aspect = (aspect + 360) % 360  # Convert to 0-360 range
            
            # Mask nodata values
            if nodata is not None:
                mask = elevation_data == nodata
                slope = np.where(mask, np.nan, slope)
                aspect = np.where(mask, np.nan, aspect)
            
            # Calculate statistics for derivatives
            valid_slope = slope[~np.isnan(slope)]
            valid_aspect = aspect[~np.isnan(aspect)]
            
            derivatives = {
                'slope_stats': {
                    'min_slope': float(np.min(valid_slope)) if len(valid_slope) > 0 else None,
                    'max_slope': float(np.max(valid_slope)) if len(valid_slope) > 0 else None,
                    'mean_slope': float(np.mean(valid_slope)) if len(valid_slope) > 0 else None,
                    'std_slope': float(np.std(valid_slope)) if len(valid_slope) > 0 else None
                },
                'aspect_stats': {
                    'mean_aspect': float(np.mean(valid_aspect)) if len(valid_aspect) > 0 else None,
                    'aspect_distribution': self._analyze_aspect_distribution(valid_aspect)
                },
                'terrain_roughness': float(np.std(valid_slope)) if len(valid_slope) > 0 else None,
                'pixel_size_meters': pixel_size
            }
            
            return derivatives
            
        except Exception as e:
            logger.error(f"Error calculating terrain derivatives: {e}")
            return {'error': str(e)}
    
    def _analyze_aspect_distribution(self, aspect_values: np.ndarray) -> Dict[str, float]:
        """Analyze aspect distribution by cardinal directions."""
        
        if len(aspect_values) == 0:
            return {}
        
        # Define cardinal direction ranges
        directions = {
            'North': ((337.5, 360), (0, 22.5)),
            'Northeast': (22.5, 67.5),
            'East': (67.5, 112.5),
            'Southeast': (112.5, 157.5),
            'South': (157.5, 202.5),
            'Southwest': (202.5, 247.5),
            'West': (247.5, 292.5),
            'Northwest': (292.5, 337.5)
        }
        
        distribution = {}
        total_pixels = len(aspect_values)
        
        for direction, ranges in directions.items():
            if direction == 'North':  # Special case for North (wraps around 0)
                count = np.sum((aspect_values >= ranges[0][0]) | (aspect_values <= ranges[1][1]))
            else:
                count = np.sum((aspect_values >= ranges[0]) & (aspect_values < ranges[1]))
            
            distribution[direction] = round((count / total_pixels) * 100, 2)
        
        return distribution


class WeatherMetadataExtractor:
    """
    Weather data metadata extraction and interpretation
    
    Structures weather data and provides fire weather analysis.
    """
    
    def __init__(self):
        """Initialize weather metadata extractor."""
        pass
    
    def extract_weather_metadata(self, weather_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract metadata from weather data
        
        Args:
            weather_data: Raw weather data from OpenWeatherMap
            
        Returns:
            Dictionary containing structured weather metadata
        """
        metadata = {
            'source': 'OpenWeatherMap',
            'extraction_time': datetime.now().isoformat(),
            'data_types': []
        }
        
        # Analyze current weather
        if 'current' in weather_data.get('data', {}):
            metadata['current_weather'] = self._analyze_current_weather(
                weather_data['data']['current']
            )
            metadata['data_types'].append('current_conditions')
        
        # Analyze forecast data
        if 'forecast' in weather_data.get('data', {}):
            metadata['forecast_analysis'] = self._analyze_forecast(
                weather_data['data']['forecast']
            )
            metadata['data_types'].append('forecast')
        
        return metadata
    
    def _analyze_current_weather(self, current_data: Dict[str, Any]) -> Dict[str, Any]: 
        """Analyze current weather conditions."""
        
        return {
            'observation_time': current_data.get('timestamp'),
            'temperature_analysis': {
                'celsius': current_data.get('temperature_celsius'),
                'fire_risk_contribution': self._assess_temperature_fire_risk(
                    current_data.get('temperature_celsius', 0)
                )
            },
            'humidity_analysis': {
                'percent': current_data.get('humidity_percent'),
                'fire_risk_contribution': self._assess_humidity_fire_risk(
                    current_data.get('humidity_percent', 100)
                )
            },
            'wind_analysis': {
                'speed_mps': current_data.get('wind_speed_mps'),
                'direction_deg': current_data.get('wind_direction_deg'),
                'fire_risk_contribution': self._assess_wind_fire_risk(
                    current_data.get('wind_speed_mps', 0)
                )
            },
            'overall_fire_weather_risk': current_data.get('fire_weather_risk'),
            'visibility_meters': current_data.get('visibility_meters'),
            'atmospheric_conditions': current_data.get('weather_description')
        }
    
    def _analyze_forecast(self, forecast_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze forecast time series."""
        
        if not forecast_data:
            return {'error': 'No forecast data available'}
        
        # Extract time series values
        temperatures = [item.get('temperature_celsius', 0) for item in forecast_data]
        humidity_values = [item.get('humidity_percent', 100) for item in forecast_data]
        wind_speeds = [item.get('wind_speed_mps', 0) for item in forecast_data]
        fire_risks = [item.get('fire_weather_risk', 'LOW') for item in forecast_data]
        
        analysis = {
            'forecast_period': {
                'start_time': forecast_data[0].get('timestamp'),
                'end_time': forecast_data[-1].get('timestamp'),
                'data_points': len(forecast_data)
            },
            'temperature_trends': {
                'min': min(temperatures),
                'max': max(temperatures),
                'mean': round(np.mean(temperatures), 1),
                'trend': self._calculate_trend(temperatures)
            },
            'humidity_trends': {
                'min': min(humidity_values),
                'max': max(humidity_values),
                'mean': round(np.mean(humidity_values), 1),
                'trend': self._calculate_trend(humidity_values)
            },
            'wind_trends': {
                'min': min(wind_speeds),
                'max': max(wind_speeds),
                'mean': round(np.mean(wind_speeds), 1),
                'trend': self._calculate_trend(wind_speeds)
            },
            'fire_risk_forecast': {
                'risk_distribution': self._count_risk_levels(fire_risks),
                'peak_risk_periods': self._identify_peak_risk_periods(forecast_data)
            }
        }
        
        return analysis
    
    def _assess_temperature_fire_risk(self, temp_celsius: float) -> str:
        """Assess fire risk contribution from temperature."""
        if temp_celsius > 30:
            return 'HIGH'
        elif temp_celsius > 25:
            return 'MODERATE' 
        elif temp_celsius > 20:
            return 'LOW'
        else:
            return 'MINIMAL'
    
    def _assess_humidity_fire_risk(self, humidity_percent: float) -> str:
        """Assess fire risk contribution from humidity."""
        if humidity_percent < 20:
            return 'HIGH'
        elif humidity_percent < 40:
            return 'MODERATE'
        elif humidity_percent < 60:
            return 'LOW'
        else:
            return 'MINIMAL'
    
    def _assess_wind_fire_risk(self, wind_speed_mps: float) -> str:
        """Assess fire risk contribution from wind speed."""
        if wind_speed_mps > 15:
            return 'HIGH'
        elif wind_speed_mps > 10:
            return 'MODERATE'
        elif wind_speed_mps > 5:
            return 'LOW'
        else:
            return 'MINIMAL'
    
    def _calculate_trend(self, values: List[float]) -> str:
        """Calculate trend direction for time series values."""
        if len(values) < 2:
            return 'STABLE'
        
        first_half = values[:len(values)//2]
        second_half = values[len(values)//2:]
        
        first_mean = np.mean(first_half)
        second_mean = np.mean(second_half)
        
        change_percent = ((second_mean - first_mean) / first_mean) * 100
        
        if change_percent > 5:
            return 'INCREASING'
        elif change_percent < -5:
            return 'DECREASING'
        else:
            return 'STABLE'
    
    def _count_risk_levels(self, fire_risks: List[str]) -> Dict[str, int]:
        """Count occurrences of each fire risk level."""
        risk_counts = {'LOW': 0, 'MODERATE': 0, 'HIGH': 0, 'EXTREME': 0}
        
        for risk in fire_risks:
            if risk in risk_counts:
                risk_counts[risk] += 1
        
        return risk_counts
    
    def _identify_peak_risk_periods(self, forecast_data: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Identify periods of elevated fire weather risk."""
        
        peak_periods = []
        current_period = None
        
        for item in forecast_data:
            risk = item.get('fire_weather_risk', 'LOW')
            timestamp = item.get('timestamp')
            
            if risk in ['HIGH', 'EXTREME']:
                if current_period is None:
                    current_period = {'start': timestamp, 'risk_level': risk}
                else:
                    # Update end time and risk level
                    current_period['end'] = timestamp
                    if risk == 'EXTREME':
                        current_period['risk_level'] = 'EXTREME'
            else:
                if current_period is not None:
                    # End of high risk period
                    if 'end' not in current_period:
                        current_period['end'] = current_period['start']
                    peak_periods.append(current_period)
                    current_period = None
        
        # Handle case where high risk period extends to end of forecast
        if current_period is not None:
            if 'end' not in current_period:
                current_period['end'] = forecast_data[-1].get('timestamp')
            peak_periods.append(current_period)
        
        return peak_periods


# Main execution functions
def extract_landfire_metadata(pipeline_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract metadata from all data sources in pipeline output
    
    Args:
        pipeline_data: Complete pipeline output data
        
    Returns:
        Dictionary containing metadata from all sources
    """
    metadata = {
        'extraction_time': datetime.now().isoformat(),
        'sources': {}
    }
    
    # Extract LANDFIRE metadata
    if 'landfire' in pipeline_data and 'data' in pipeline_data['landfire']:
        landfire_extractor = LANDFIREMetadataExtractor()
        metadata['sources']['landfire'] = {}
        
        for product_name, product_data in pipeline_data['landfire']['data'].items():
            if isinstance(product_data, dict) and 'data' in product_data:
                metadata['sources']['landfire'][product_name] = landfire_extractor.extract_raster_metadata(
                    product_data['data'], product_name
                )
    
    # Extract MODIS metadata
    if 'modis' in pipeline_data and 'data' in pipeline_data['modis']:
        modis_extractor = MODISMetadataExtractor()
        metadata['sources']['modis'] = modis_extractor.extract_time_series_metadata(
            pipeline_data['modis']
        )
    
    # Extract USGS elevation metadata
    if 'elevation' in pipeline_data and 'data' in pipeline_data['elevation']:
        elevation_extractor = USGSElevationMetadataExtractor()
        elevation_data = pipeline_data['elevation']['data']
        
        if 'elevation' in elevation_data and 'data' in elevation_data['elevation']:
            metadata['sources']['elevation'] = elevation_extractor.extract_elevation_metadata(
                elevation_data['elevation']['data']
            )
    
    # Extract weather metadata
    if 'weather' in pipeline_data and 'data' in pipeline_data['weather']:
        weather_extractor = WeatherMetadataExtractor()
        metadata['sources']['weather'] = weather_extractor.extract_weather_metadata(
            pipeline_data['weather']
        )
    
    return metadata


def main():
    """Demonstrate metadata extraction functionality."""
    
    print("Geospatial Data Pipeline - Metadata Extraction")
    print("=" * 50)
    
    # Example usage with pipeline data
    from pipeline import GeospatialDataPipeline
    
    # Get sample data
    pipeline = GeospatialDataPipeline(landfire_year='latest')
    sample_data = pipeline.get_location_data(34.0522, -118.2437, buffer_meters=500)
    
    # Extract all metadata
    metadata = extract_all_metadata(sample_data)
    
    # Save metadata to file
    metadata_filename = f"metadata_extract_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(metadata_filename, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"Metadata extracted and saved to: {metadata_filename}")
    
    # Print summary
    print("\nMetadata Summary:")
    for source, source_metadata in metadata.get('sources', {}).items():
        print(f"  {source.upper()}: {len(source_metadata)} components analyzed")


if __name__ == "__main__":
    main()