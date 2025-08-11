"""
Metadata Services

Handles extraction and interpretation of geospatial data metadata,
including LANDFIRE attribute tables and MODIS value scaling.
"""

from .landfire_interpretation import LANDFIREMetadataExtractor, extract_landfire_metadata
from .modis_interpretation import (
    build_modis_scaling_table,
    build_quality_flag_interpretation,
    apply_modis_scaling,
    interpret_quality_flag
)
from .metadata_integration import extract_all_metadata

__all__ = [
    "LANDFIREMetadataExtractor",
    "extract_landfire_metadata",
    "extract_all_metadata",
    "build_modis_scaling_table",
    "build_quality_flag_interpretation", 
    "apply_modis_scaling",
    "interpret_quality_flag"
]