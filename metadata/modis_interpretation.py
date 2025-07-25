"""
MODIS Data Interpretation Module

Handles scaling, quality flag interpretation, and value conversion
for MODIS satellite data products.
"""

from typing import Dict, Any, List, Tuple
import numpy as np


def build_modis_scaling_table() -> Dict[str, Dict[str, Any]]:
    """
    Build scaling factors and valid ranges for MODIS products.
    
    MODIS products use scale factors to convert integer values to physical units:
    - NDVI/EVI: scale_factor = 0.0001, valid_range = [-2000, 10000]
    - LAI/FPAR: scale_factor = 0.1, valid_range = [0, 100]
    - LST: scale_factor = 0.02, offset = 273.15, valid_range = [7500, 65535]
    
    Returns:
        Dictionary with scaling factors and valid ranges for each MODIS product
    """
    return {
        'MOD13Q1': {  # Vegetation Indices
            '250m_16_days_NDVI': {
                'scale_factor': 0.0001,
                'valid_range': [-2000, 10000],
                'fill_value': -3000,
                'units': 'NDVI'
            },
            '250m_16_days_EVI': {
                'scale_factor': 0.0001,
                'valid_range': [-2000, 10000],
                'fill_value': -3000,
                'units': 'EVI'
            }
        },
        'MYD13Q1': {  # Vegetation Indices (Aqua)
            '250m_16_days_NDVI': {
                'scale_factor': 0.0001,
                'valid_range': [-2000, 10000],
                'fill_value': -3000,
                'units': 'NDVI'
            },
            '250m_16_days_EVI': {
                'scale_factor': 0.0001,
                'valid_range': [-2000, 10000],
                'fill_value': -3000,
                'units': 'EVI'
            }
        },
        'MOD15A2H': {  # LAI/FPAR
            'Lai_500m': {
                'scale_factor': 0.1,
                'valid_range': [0, 100],
                'fill_value': 255,
                'units': 'm^2/m^2'
            },
            'Fpar_500m': {
                'scale_factor': 0.01,
                'valid_range': [0, 100],
                'fill_value': 255,
                'units': 'fraction'
            }
        },
        'MYD15A2H': {  # LAI/FPAR (Aqua)
            'Lai_500m': {
                'scale_factor': 0.1,
                'valid_range': [0, 100],
                'fill_value': 255,
                'units': 'm^2/m^2'
            },
            'Fpar_500m': {
                'scale_factor': 0.01,
                'valid_range': [0, 100],
                'fill_value': 255,
                'units': 'fraction'
            }
        },
        'MOD11A2': {  # Land Surface Temperature
            'LST_Day_1km': {
                'scale_factor': 0.02,
                'offset': 273.15,
                'valid_range': [7500, 65535],
                'fill_value': 0,
                'units': 'Kelvin'
            },
            'LST_Night_1km': {
                'scale_factor': 0.02,
                'offset': 273.15,
                'valid_range': [7500, 65535],
                'fill_value': 0,
                'units': 'Kelvin'
            }
        },
        'MYD11A2': {  # Land Surface Temperature (Aqua)
            'LST_Day_1km': {
                'scale_factor': 0.02,
                'offset': 273.15,
                'valid_range': [7500, 65535],
                'fill_value': 0,
                'units': 'Kelvin'
            },
            'LST_Night_1km': {
                'scale_factor': 0.02,
                'offset': 273.15,
                'valid_range': [7500, 65535],
                'fill_value': 0,
                'units': 'Kelvin'
            }
        },
        'MOD17A2H': {  # Gross Primary Productivity
            'Gpp_500m': {
                'scale_factor': 0.0001,
                'valid_range': [0, 30000],
                'fill_value': 65535,
                'units': 'kg C/m^2/8day'
            }
        },
        'MYD17A2H': {  # Gross Primary Productivity (Aqua)
            'Gpp_500m': {
                'scale_factor': 0.0001,
                'valid_range': [0, 30000],
                'fill_value': 65535,
                'units': 'kg C/m^2/8day'
            }
        }
    }


def build_quality_flag_interpretation() -> Dict[str, Dict[int, str]]:
    """
    Build interpretation tables for MODIS data quality flags.
    
    MODIS products include quality flags that indicate data reliability,
    cloud cover, aerosol conditions, etc.
    
    Returns:
        Dictionary mapping quality flag values to interpretations
    """
    return {
        'MOD13Q1_reliability': {
            0: 'Good data, use with confidence',
            1: 'Marginal data, useful but look at detailed QA for more information',
            2: 'Snow/ice target',
            3: 'Cloudy data'
        },
        'MOD15A2H_quality': {
            0: 'Good quality (main algorithm with or without saturation)',
            1: 'Other quality (backup algorithm or fill values)',
            2: 'TBD',
            3: 'TBD'
        },
        'MOD11A2_quality': {
            0: 'Good quality LST',
            1: 'Other quality data',
            2: 'TBD',
            3: 'TBD'
        }
    }


def apply_modis_scaling(raw_value: int, product: str, layer: str) -> float:
    """
    Apply MODIS scaling factors to convert raw integer values to physical units.
    
    Args:
        raw_value: Raw integer value from MODIS data
        product: MODIS product name (e.g., 'MOD13Q1')
        layer: Layer name (e.g., '250m_16_days_NDVI')
        
    Returns:
        Scaled value in physical units
    """
    scaling_table = build_modis_scaling_table()
    
    if product not in scaling_table or layer not in scaling_table[product]:
        return raw_value  # Return unscaled if no scaling info available
    
    scaling_info = scaling_table[product][layer]
    
    # Check for fill values
    if raw_value == scaling_info.get('fill_value', -9999):
        return np.nan
    
    # Check valid range
    valid_range = scaling_info.get('valid_range', [None, None])
    if (valid_range[0] is not None and raw_value < valid_range[0]) or \
       (valid_range[1] is not None and raw_value > valid_range[1]):
        return np.nan
    
    # Apply scaling
    scaled_value = raw_value * scaling_info['scale_factor']
    
    # Apply offset if present (for temperature data)
    if 'offset' in scaling_info:
        scaled_value += scaling_info['offset']
    
    return scaled_value


def interpret_quality_flag(flag_value: int, product: str, flag_type: str = 'reliability') -> str:
    """
    Interpret MODIS quality flag values.
    
    Args:
        flag_value: Quality flag integer value
        product: MODIS product name
        flag_type: Type of quality flag
        
    Returns:
        Human-readable interpretation of the quality flag
    """
    quality_flags = build_quality_flag_interpretation()
    
    flag_key = f"{product}_{flag_type}"
    
    if flag_key in quality_flags and flag_value in quality_flags[flag_key]:
        return quality_flags[flag_key][flag_value]
    
    return f"Unknown quality flag: {flag_value}"